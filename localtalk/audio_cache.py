import hashlib
import io
import json
import os
import re
import wave
from pathlib import Path
from tempfile import NamedTemporaryFile

from .config import BASE


AUDIO_CACHE_VERSION = 1
AUDIO_HISTORY_LIMIT = 100
AUDIO_FILE = re.compile(r"segment-(?:[0-9a-f]{32}|[0-9a-f]{64}|\d{20})\.wav")


def audio_key(text, identity):
    value = json.dumps(
        {"version": AUDIO_CACHE_VERSION, "text": text, "tts": identity},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.blake2b(value.encode("utf-8"), digest_size=16).hexdigest()


class AudioCache:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser()
        if not self.directory.is_absolute():
            self.directory = BASE / self.directory

    def load(self, key):
        path = self.directory / f"segment-{key}.wav"
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return None
        try:
            with wave.open(io.BytesIO(data), "rb") as audio:
                frames, sample_rate = audio.getnframes(), audio.getframerate()
                width, channels = audio.getsampwidth(), audio.getnchannels()
                if (
                    not frames
                    or sample_rate <= 0
                    or width != 2
                    or len(audio.readframes(frames)) != frames * width * channels
                ):
                    raise ValueError("缓存没有完整的 PCM16 音频。")
        except (wave.Error, EOFError, ValueError):
            path.unlink(missing_ok=True)
            return None
        try:
            os.utime(path, None)
        except FileNotFoundError:
            pass
        return data, frames / sample_rate

    def save(self, key, data):
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(
                dir=self.directory, prefix=".segment-", suffix=".tmp", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(data)
            os.replace(temporary, self.directory / f"segment-{key}.wav")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        files = sorted(
            (
                path
                for path in self.directory.iterdir()
                if path.is_file() and AUDIO_FILE.fullmatch(path.name)
            ),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )
        for path in files[:-AUDIO_HISTORY_LIMIT]:
            path.unlink(missing_ok=True)
