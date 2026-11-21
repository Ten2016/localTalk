import io
import json
import os
import queue
import re
import threading
from pathlib import Path
from time import perf_counter

import requests
import sherpa_onnx
import soundfile as sf

if os.name == "nt":
    import winsound


BASE = Path(__file__).resolve().parent
VERSION = "0.1.0"
SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "你是一个中文语音助手。请使用自然、口语化的中文交流。"
        "日常问题简洁回答；用户要求故事、详细解释或完整内容时充分回答。"
        "回答需要直接朗读，避免Markdown表格、星号和表情符号。"
        "不知道的内容请明确说明，不编造实时信息或已执行的操作。"
    ),
}
SENTENCE_END = re.compile(r"[。！？!?；;\n]|\.(?=\s)")
FIRST_CHUNK_END = re.compile(r"[，：]|(?<!\d)[,:]|" + SENTENCE_END.pattern)


def load_config():
    config_path = BASE / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(
            "请先复制 config.example.json 为 config.json，并配置模型目录。"
        )
    with config_path.open(encoding="utf-8-sig") as handle:
        config = json.load(handle)
    positive_ints = (
        "context_tokens",
        "max_output_tokens",
        "tts_threads",
        "first_chunk_chars",
        "chunk_chars",
    )
    for name in positive_ints:
        if type(config[name]) is not int or config[name] <= 0:
            raise ValueError(f"config.json 中 {name} 必须为正整数。")
    if config["context_tokens"] <= config["max_output_tokens"] + 512:
        raise ValueError("上下文窗口必须为输入保留足够空间。")
    if min(config["first_chunk_chars"], config["chunk_chars"]) < 12:
        raise ValueError("文本分段上限至少为 12 个字符。")
    if not 0 < config["speech_speed"] <= 3:
        raise ValueError("speech_speed 必须大于 0 且不超过 3。")
    if type(config["speaker_id"]) is not int or not 0 <= config["speaker_id"] <= 102:
        raise ValueError("Kokoro v1.1 的 speaker_id 范围是 0～102。")
    return config


def create_tts(config):
    model_dir = Path(config["tts_model_dir"]).expanduser()
    if not model_dir.is_absolute():
        model_dir = BASE / model_dir

    def path(name):
        result = model_dir / name
        if not result.exists():
            raise FileNotFoundError(f"缺少 TTS 模型文件或目录：{result}")
        return str(result)

    tts_config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=path("model.onnx"),
                voices=path("voices.bin"),
                tokens=path("tokens.txt"),
                data_dir=path("espeak-ng-data"),
                lexicon=",".join([path("lexicon-us-en.txt"), path("lexicon-zh.txt")]),
            ),
            provider="cpu",
            num_threads=config["tts_threads"],
        ),
        max_num_sentences=1,
    )
    if not tts_config.validate():
        raise ValueError("TTS 配置校验失败。")
    return sherpa_onnx.OfflineTts(tts_config)


class TextChunks:
    def __init__(self, config):
        self.config = config
        self.buffer = ""
        self.first = True

    def feed(self, text, final=False):
        self.buffer += text
        while self.buffer:
            limit = self.config["first_chunk_chars" if self.first else "chunk_chars"]
            end = 0
            pattern = FIRST_CHUNK_END if self.first else SENTENCE_END
            minimum = 1 if self.first else 12
            for match in pattern.finditer(self.buffer):
                if minimum <= match.end() <= limit and re.search(
                    r"\w", self.buffer[: match.end()]
                ):
                    end = match.end()
                    break
            if not end and len(self.buffer) >= limit:
                # 长句优先在逗号或空格处分段；没有边界时保留全部字符硬切。
                boundaries = list(re.finditer(r"[，,、：:\s]", self.buffer[:limit]))
                end = boundaries[-1].end() if boundaries else limit
                if end < limit // 2:
                    end = limit
            if not end:
                if not final:
                    break
                end = len(self.buffer)
            chunk, self.buffer = self.buffer[:end], self.buffer[end:]
            if chunk.strip():
                self.first = False
                yield chunk


def input_size(messages):
    # 保守估算，不声称精确 token 计数；另为模板预留固定开销。
    return 256 + sum(len(item["content"].encode("utf-8")) + 64 for item in messages)


def prepare_messages(config, history, question):
    user_message = {"role": "user", "content": question}
    budget = config["context_tokens"] - config["max_output_tokens"] - 512
    if input_size([SYSTEM_MESSAGE, user_message]) > budget:
        raise ValueError("本次输入过长，请拆分发送。")
    retained = history.copy()
    while (
        retained and input_size([SYSTEM_MESSAGE] + retained + [user_message]) > budget
    ):
        retained = retained[2:]
    removed = (len(history) - len(retained)) // 2
    if removed:
        print(f"本轮请求将省略最早的 {removed} 轮历史。")
    return [SYSTEM_MESSAGE] + retained + [user_message]


class SpeechPipeline:
    def __init__(self, tts, config, start):
        self.tts = tts
        self.config = config
        self.start = start
        self.cancelled = threading.Event()
        self.errors = queue.Queue()
        self.text_queue = queue.Queue(maxsize=4)
        self.audio_queue = queue.Queue(maxsize=3)
        self.synthesis_seconds = 0.0
        self.audio_seconds = 0.0
        self.first_play_seconds = None
        self.played_chunks = 0
        self.threads = [
            threading.Thread(target=self.synthesize, name="tts-synthesis"),
            threading.Thread(target=self.play, name="audio-playback"),
        ]
        for thread in self.threads:
            thread.start()

    def put(self, target, item):
        while not self.cancelled.is_set():
            try:
                target.put(item, timeout=0.1)
                return
            except queue.Full:
                continue
        self.check()
        raise RuntimeError("语音流水线已取消。")

    def get(self, source):
        while not self.cancelled.is_set():
            try:
                return source.get(timeout=0.1)
            except queue.Empty:
                continue
        return None

    def fail(self, stage, exc):
        self.errors.put(RuntimeError(f"{stage}失败：{exc}"))
        self.cancelled.set()

    def check(self):
        if not self.errors.empty():
            raise self.errors.get()

    def synthesize(self):
        try:
            while not self.cancelled.is_set():
                text = self.get(self.text_queue)
                if text is None:
                    break
                text = text.translate(str.maketrans("", "", "\u201c\u201d")).strip()
                if not text:
                    continue
                start = perf_counter()
                audio = self.tts.generate(
                    text=text,
                    sid=self.config["speaker_id"],
                    speed=self.config["speech_speed"],
                )
                self.synthesis_seconds += perf_counter() - start
                if len(audio.samples) == 0:
                    raise RuntimeError("该文本片段没有生成音频。")
                self.audio_seconds += len(audio.samples) / audio.sample_rate
                self.put(self.audio_queue, (audio.samples, audio.sample_rate))
            if not self.cancelled.is_set():
                self.put(self.audio_queue, None)
        except Exception as exc:
            self.fail("语音合成", exc)

    def play(self):
        output = None
        try:
            while not self.cancelled.is_set():
                item = self.get(self.audio_queue)
                if item is None:
                    break
                samples, sample_rate = item
                buffer = io.BytesIO()
                sf.write(buffer, samples, sample_rate, format="WAV", subtype="PCM_16")
                if self.cancelled.is_set():
                    break
                if output is None:
                    output_dir = BASE / "output"
                    output_dir.mkdir(exist_ok=True)
                    output = sf.SoundFile(
                        str(output_dir / "last_reply.wav"),
                        mode="w",
                        samplerate=sample_rate,
                        channels=1,
                        subtype="PCM_16",
                    )
                if self.first_play_seconds is None:
                    self.first_play_seconds = perf_counter() - self.start
                winsound.PlaySound(
                    buffer.getvalue(), winsound.SND_MEMORY | winsound.SND_SYNC
                )
                output.write(samples)
                output.flush()
                self.played_chunks += 1
        except Exception as exc:
            self.fail("音频播放", exc)
        finally:
            if output is not None:
                output.close()

    def finish(self):
        self.put(self.text_queue, None)
        for thread in self.threads:
            thread.join()
        self.check()

    def cancel(self):
        self.cancelled.set()
        # 当前同步合成或播放完成后退出，不复用仍在工作的 TTS 实例。
        for thread in self.threads:
            thread.join()


def run_turn(session, tts, config, messages):
    start = perf_counter()
    pipeline = SpeechPipeline(tts, config, start)
    chunker = TextChunks(config)
    answer = []
    final_result = None
    first_text_seconds = None
    print("\n助手：", end="", flush=True)
    try:
        with session.post(
            config["ollama_url"],
            json={
                "model": config["model"],
                "messages": messages,
                "think": False,
                "stream": True,
                "keep_alive": "10m",
                "options": {
                    "num_ctx": config["context_tokens"],
                    "num_predict": config["max_output_tokens"],
                    "temperature": 0.7,
                    "top_p": 0.8,
                    "top_k": 20,
                    "min_p": 0.0,
                    "presence_penalty": 1.5,
                    "repeat_penalty": 1.0,
                },
            },
            stream=True,
            timeout=(5, 120),
        ) as response:
            if not response.ok:
                raise RuntimeError(
                    f"Ollama HTTP {response.status_code}：{response.text[:1000]}"
                )
            for line in response.iter_lines(chunk_size=1):
                pipeline.check()
                if not line:
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise RuntimeError(data["error"])
                text = data.get("message", {}).get("content", "")
                if text:
                    if first_text_seconds is None:
                        first_text_seconds = perf_counter() - start
                    answer.append(text)
                    print(text, end="", flush=True)
                    for chunk in chunker.feed(text):
                        pipeline.put(pipeline.text_queue, chunk)
                if data.get("done"):
                    final_result = data
                    break
        if final_result is None:
            raise RuntimeError("Ollama 流意外中断，回答不完整。")
        full_answer = "".join(answer).strip()
        if not full_answer:
            raise RuntimeError("Ollama 返回了空回答。")
        for chunk in chunker.feed("", final=True):
            pipeline.put(pipeline.text_queue, chunk)
        print("\n", flush=True)
        if final_result.get("done_reason") == "length":
            print("提示：回答达到输出上限，可能未说完。")
        pipeline.finish()
        if pipeline.first_play_seconds is None:
            raise RuntimeError("回答中没有可朗读的文本。")
    except BaseException:
        pipeline.cancel()
        raise

    print(
        f"首段文本：{first_text_seconds:.2f} 秒；"
        f"首段提交播放：{pipeline.first_play_seconds:.2f} 秒；"
        f"已播放：{pipeline.played_chunks} 段"
    )
    print(
        f"累计合成：{pipeline.synthesis_seconds:.2f} 秒；"
        f"音频长度：{pipeline.audio_seconds:.2f} 秒；"
        f"实时率：{pipeline.synthesis_seconds / pipeline.audio_seconds:.2f}"
    )
    print(
        f"输入：{final_result.get('prompt_eval_count', '?')} tokens；"
        f"输出：{final_result.get('eval_count', '?')} tokens\n"
    )
    return full_answer


def main():
    if os.name != "nt":
        raise RuntimeError("当前播放实现面向 Windows，请在 Win10 电脑上运行。")
    config = load_config()
    print(f"LocalTalk {VERSION} · 本地语音助手")
    print("正在加载 CPU 语音模型……", flush=True)
    tts = create_tts(config)
    print(f"模型：{config['model']}")
    print(
        f"上下文：{config['context_tokens']}；最大输出：{config['max_output_tokens']}"
    )
    print("输入问题开始对话；/clear 清空历史；/quit 退出。")
    history = []
    with requests.Session() as session:
        if config["ollama_url"].startswith(("http://127.0.0.1:", "http://localhost:")):
            session.trust_env = False
        while True:
            question = input("\n你：").strip()
            if not question:
                continue
            if question == "/quit":
                return
            if question == "/clear":
                history.clear()
                print("对话历史已清空。")
                continue
            try:
                messages = prepare_messages(config, history, question)
                answer = run_turn(session, tts, config, messages)
            except (
                requests.RequestException,
                RuntimeError,
                ValueError,
                OSError,
            ) as exc:
                print(f"\n本轮未完成：{exc}\n已停止排队音频，本轮不写入对话历史。")
                continue
            history = messages[1:] + [{"role": "assistant", "content": answer}]


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n已退出。")
