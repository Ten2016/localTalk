import io
import os
import queue
import threading
from time import perf_counter

from .audio_cache import AudioCache, audio_key

if os.name == "nt":
    import winsound


class SpeechPipeline:
    def __init__(self, tts, config, start):
        self.tts = tts
        self.config = config["tts"]
        self.start = start
        self.cache = AudioCache(self.config["audio_output_dir"])
        self.cancelled = threading.Event()
        self.errors = queue.Queue()
        # 只排队文本，避免音频反压阻塞 Ollama 读取；单轮输出已有 token 上限。
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue(maxsize=3)
        self.synthesis_seconds = 0.0
        self.audio_seconds = 0.0
        self.generated_audio_seconds = 0.0
        self.cache_hits = 0
        self.first_play_seconds = None
        self.played_chunks = 0
        self.playback_gap_seconds = 0.0
        self.max_playback_gap_seconds = 0.0
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
            import soundfile as sf

            while not self.cancelled.is_set():
                text = self.get(self.text_queue)
                if text is None:
                    break
                if self.config["backend"] != "volcengine":
                    text = text.translate(str.maketrans("", "", "\u201c\u201d"))
                text = text.strip()
                if not text:
                    continue
                key = audio_key(text, self.tts.cache_identity)
                cached = self.cache.load(key)
                if cached is None:
                    start = perf_counter()
                    samples, sample_rate = self.tts.generate(text)
                    self.synthesis_seconds += perf_counter() - start
                    if len(samples) == 0 or sample_rate <= 0:
                        raise RuntimeError("该文本片段没有生成音频。")
                    duration = len(samples) / sample_rate
                    self.generated_audio_seconds += duration
                    buffer = io.BytesIO()
                    sf.write(
                        buffer, samples, sample_rate, format="WAV", subtype="PCM_16"
                    )
                    wav_bytes = buffer.getvalue()
                    if self.cancelled.is_set():
                        break
                    self.cache.save(key, wav_bytes)
                else:
                    wav_bytes, duration = cached
                    self.cache_hits += 1
                self.audio_seconds += duration
                self.put(self.audio_queue, wav_bytes)
            if not self.cancelled.is_set():
                self.put(self.audio_queue, None)
        except Exception as exc:
            self.fail("语音合成", exc)

    def play(self):
        previous_play_end = None
        try:
            while not self.cancelled.is_set():
                wav_bytes = self.get(self.audio_queue)
                if wav_bytes is None:
                    break
                if self.cancelled.is_set():
                    break
                if self.first_play_seconds is None:
                    self.first_play_seconds = perf_counter() - self.start
                if previous_play_end is not None:
                    gap = perf_counter() - previous_play_end
                    self.playback_gap_seconds += gap
                    self.max_playback_gap_seconds = max(
                        self.max_playback_gap_seconds, gap
                    )
                winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
                previous_play_end = perf_counter()
                self.played_chunks += 1
        except Exception as exc:
            self.fail("音频播放", exc)

    def finish(self):
        self.put(self.text_queue, None)
        for thread in self.threads:
            thread.join()
        self.check()

    def cancel(self):
        self.cancelled.set()
        # 当前同步合成或播放完成后退出；HTTP 请求受连接和读取超时限制。
        for thread in self.threads:
            thread.join()
