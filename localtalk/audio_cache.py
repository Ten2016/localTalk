import hashlib
import io
import json
import os
import re
import wave
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from tempfile import NamedTemporaryFile

from .config import BASE


AUDIO_CACHE_VERSION = 1
AUDIO_HISTORY_LIMIT = 1000
AUDIO_FILE = re.compile(r"[0-9a-f]{32}\.wav")


def directory_name(value):
    name = str(value)
    if (
        not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", name)
        or name.endswith(".")
        or PureWindowsPath(name).is_reserved()
    ):
        raise ValueError(
            "缓存目录名仅支持字母、数字、下划线、连字符和内部句点，不能使用 Windows 保留名称。"
        )
    return name


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class AudioCache:
    def __init__(self, directory, identity):
        self.directory = Path(directory).expanduser()
        if not self.directory.is_absolute():
            self.directory = BASE / self.directory
        self.parameters = dict(identity)
        backend = directory_name(self.parameters.pop("backend"))
        model = directory_name(self.parameters.pop("model"))
        voice = directory_name(self.parameters.pop("voice"))
        self.scope = Path(backend) / model / voice
        self.index_path = self.directory / "index.json"
        try:
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            index = {}
        self.records = {
            Path(backend) / model / voice / filename: record
            for backend, models in index.items()
            for model, voices in models.items()
            for voice, files in voices.items()
            for filename, record in files.items()
        }
        if self.directory.exists():
            self.prune()
            self.write_index()

    def key(self, text):
        value = json.dumps(
            {"version": AUDIO_CACHE_VERSION, "text": text, "tts": self.parameters},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        digest = hashlib.blake2b(value.encode("utf-8"), digest_size=16).hexdigest()
        return self.scope / f"{digest}.wav"

    def load(self, key):
        path = self.directory / key
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
        self.record_use(key)
        self.write_index()
        return data, frames / sample_rate

    def save(self, key, data):
        write_atomic(self.directory / key, data)
        self.record_use(key)
        self.prune()
        self.write_index()

    def record_use(self, key):
        previous = self.records.get(key, {})
        self.records[key] = {
            "use_count": previous.get("use_count", 0) + 1,
            "last_used_at": datetime.now(UTC).isoformat(timespec="microseconds"),
        }

    def prune(self):
        records = {}
        for path in self.directory.glob("*/*/*/*.wav"):
            if not path.is_file() or not AUDIO_FILE.fullmatch(path.name):
                continue
            key = path.relative_to(self.directory)
            record = self.records.get(key)
            if record is None:
                record = {
                    "use_count": 0,
                    "last_used_at": datetime.fromtimestamp(
                        path.stat().st_mtime, UTC
                    ).isoformat(timespec="microseconds"),
                }
            records[key] = record
        self.records = records
        oldest = sorted(
            self.records,
            key=lambda key: (self.records[key]["last_used_at"], key.as_posix()),
        )
        for key in oldest[:-AUDIO_HISTORY_LIMIT]:
            (self.directory / key).unlink(missing_ok=True)
            del self.records[key]

    def write_index(self):
        index = {}
        for key, record in self.records.items():
            backend, model, voice, filename = key.parts
            files = (
                index.setdefault(backend, {})
                .setdefault(model, {})
                .setdefault(voice, {})
            )
            files[filename] = record
        data = json.dumps(index, ensure_ascii=False, indent=2) + "\n"
        write_atomic(self.index_path, data.encode("utf-8"))
