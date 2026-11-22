import io
import os
import queue
import re
import threading
from pathlib import Path
from time import perf_counter, time_ns

from .config import BASE

if os.name == "nt":
    import winsound


AUDIO_HISTORY_LIMIT = 100


def save_audio_segment(wav_bytes, output_dir):
    directory = Path(output_dir).expanduser()
    if not directory.is_absolute():
        directory = BASE / directory
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"segment-{time_ns():020d}.wav").open("xb") as handle:
        handle.write(wav_bytes)
    files = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and re.fullmatch(r"segment-\d{20}\.wav", path.name)
    )
    for path in files[:-AUDIO_HISTORY_LIMIT]:
        path.unlink()


class SpeechPipeline:
    def __init__(self, tts, config, start, save_audio=True):
        self.tts = tts
        self.config = config
        self.start = start
        self.save_audio = save_audio
        self.cancelled = threading.Event()
        self.errors = queue.Queue()
        # 只排队文本，避免音频反压阻塞 Ollama 读取；单轮输出已有 token 上限。
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue(maxsize=3)
        self.synthesis_seconds = 0.0
        self.audio_seconds = 0.0
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
            while not self.cancelled.is_set():
                text = self.get(self.text_queue)
                if text is None:
                    break
                text = text.translate(str.maketrans("", "", "\u201c\u201d")).strip()
                if not text:
                    continue
                start = perf_counter()
                samples, sample_rate = self.tts.generate(text)
                self.synthesis_seconds += perf_counter() - start
                if len(samples) == 0 or sample_rate <= 0:
                    raise RuntimeError("该文本片段没有生成音频。")
                self.audio_seconds += len(samples) / sample_rate
                self.put(self.audio_queue, (samples, sample_rate))
            if not self.cancelled.is_set():
                self.put(self.audio_queue, None)
        except Exception as exc:
            self.fail("语音合成", exc)

    def play(self):
        previous_play_end = None
        try:
            import soundfile as sf

            while not self.cancelled.is_set():
                item = self.get(self.audio_queue)
                if item is None:
                    break
                samples, sample_rate = item
                buffer = io.BytesIO()
                sf.write(buffer, samples, sample_rate, format="WAV", subtype="PCM_16")
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
                winsound.PlaySound(buffer.getvalue(), winsound.SND_MEMORY)
                previous_play_end = perf_counter()
                if self.save_audio:
                    save_audio_segment(
                        buffer.getvalue(), self.config["audio_output_dir"]
                    )
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
        # 当前同步合成或播放完成后退出，不复用仍在工作的 TTS 实例。
        for thread in self.threads:
            thread.join()
