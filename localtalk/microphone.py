import math
from collections import deque
from time import perf_counter

from .asr import QwenASR
from .vad import SileroVAD


class VoiceInput:
    def __init__(self, config):
        import numpy as np
        import sounddevice as sd

        self.np = np
        self.sd = sd
        self.device = config["input"]["microphone_device"]
        sd.check_input_settings(
            device=self.device, channels=1, dtype="float32", samplerate=16000
        )
        self.vad = SileroVAD(config["vad"]["silero"])
        self.asr = QwenASR(config["asr"]["qwen3"])
        self.config = config["vad"]

    def record(self):
        self.vad.reset()
        frame_ms = self.vad.frame_samples * 1000 / self.vad.sample_rate
        pre_roll = deque(maxlen=math.ceil(self.config["pre_roll_ms"] / frame_ms) + 1)
        min_speech = math.ceil(self.config["min_speech_ms"] / frame_ms)
        end_silence = math.ceil(self.config["end_silence_ms"] / frame_ms)
        max_frames = math.ceil(self.config["max_utterance_seconds"] * 1000 / frame_ms)
        frames = []
        speech_frames = silence_frames = 0
        print("\n正在监听，说完停顿后自动提交；Ctrl+C 返回键盘输入。", flush=True)
        with self.sd.InputStream(
            device=self.device,
            channels=1,
            samplerate=self.vad.sample_rate,
            blocksize=self.vad.frame_samples,
            dtype="float32",
        ) as microphone:
            while True:
                samples, overflowed = microphone.read(self.vad.frame_samples)
                if overflowed:
                    raise RuntimeError("麦克风采集溢出，录音可能缺失，本轮没有提交。")
                frame = samples[:, 0].copy()
                pre_roll.append(frame)
                probability = self.vad.probability(frame)
                if not frames:
                    if probability < self.vad.threshold:
                        continue
                    frames = list(pre_roll)
                else:
                    frames.append(frame)
                if probability >= self.vad.threshold:
                    speech_frames += 1
                    silence_frames = 0
                elif probability < max(0.01, self.vad.threshold - 0.15):
                    silence_frames += 1
                else:
                    silence_frames = 0
                if silence_frames >= end_silence:
                    if speech_frames >= min_speech:
                        # 保留段内停顿和结尾静音，避免按帧剪掉首尾发音。
                        return self.np.concatenate(frames)
                    frames = []
                    speech_frames = silence_frames = 0
                if len(frames) >= max_frames:
                    raise RuntimeError(
                        "连续录音达到时长上限，本轮没有提交；请分次提问或使用键盘。"
                    )

    def listen(self):
        try:
            samples = self.record()
        except self.sd.PortAudioError as exc:
            raise RuntimeError(f"麦克风采集失败：{exc}") from exc
        print("正在本地识别……", flush=True)
        start = perf_counter()
        text = self.asr.transcribe(samples)
        print(f"你：{text}\n识别耗时：{perf_counter() - start:.2f} 秒", flush=True)
        return text
