import json
import math
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def validate_voice_config(config):
    for name in ("input", "asr", "vad"):
        if not isinstance(config.get(name), dict):
            raise ValueError(f"config.json 缺少 {name} 分组，请按新版配置整理。")
    if config["input"].get("mode") not in ("keyboard", "voice"):
        raise ValueError("input.mode 仅支持 keyboard 或 voice。")
    if "microphone_device" not in config["input"]:
        raise ValueError("input.microphone_device 必须配置为 null 或输入设备编号。")
    device = config["input"]["microphone_device"]
    if device is not None and (type(device) is not int or device < 0):
        raise ValueError("input.microphone_device 必须为 null 或非负设备编号。")
    for name, backend, path_name in (
        ("asr", "qwen3", "model_dir"),
        ("vad", "silero", "model_path"),
    ):
        group = config[name]
        if group.get("backend") != backend or not isinstance(group.get(backend), dict):
            raise ValueError(f"{name}.backend 仅支持 {backend}，并需要对应配置子组。")
        path = group[backend].get(path_name)
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"{name}.{backend}.{path_name} 必须为非空路径。")
    asr = config["asr"]["qwen3"]
    if type(asr.get("threads")) is not int or asr["threads"] <= 0:
        raise ValueError("asr.qwen3.threads 必须为正整数。")
    if not isinstance(asr.get("language"), str):
        raise ValueError("asr.qwen3.language 必须为字符串，留空自动识别。")
    threshold = config["vad"]["silero"].get("threshold")
    if (
        type(threshold) not in (int, float)
        or not math.isfinite(threshold)
        or not 0 < threshold < 1
    ):
        raise ValueError("vad.silero.threshold 必须在 0 和 1 之间。")
    for name, lower, upper in (
        ("min_speech_ms", 32, 1000),
        ("end_silence_ms", 100, 3000),
        ("pre_roll_ms", 160, 1000),
        ("max_utterance_seconds", 5, 30),
    ):
        value = config["vad"].get(name)
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f"vad.{name} 必须为 {lower}～{upper} 的整数。")


def load_config():
    config_path = BASE / "config.json"
    if not config_path.exists():
        raise FileNotFoundError("缺少 config.json，请从仓库恢复该文件并配置模型目录。")
    with config_path.open(encoding="utf-8-sig") as handle:
        config = json.load(handle)
    if not isinstance(config, dict) or any(
        not isinstance(config.get(name), dict) for name in ("llm", "tts")
    ):
        raise ValueError("config.json 需要 llm 和 tts 分组，请按新版配置整理原有设置。")
    llm, tts = config["llm"], config["tts"]
    for prefix, group, names in (
        ("llm", llm, ("url", "model")),
        ("tts", tts, ("audio_output_dir",)),
    ):
        for name in names:
            if not isinstance(group.get(name), str) or not group[name].strip():
                raise ValueError(f"{prefix}.{name} 必须为非空字符串。")
    for prefix, group, names in (
        ("llm", llm, ("context_tokens", "max_output_tokens")),
        ("tts", tts, ("chunk_chars",)),
    ):
        for name in names:
            if type(group.get(name)) is not int or group[name] <= 0:
                raise ValueError(f"{prefix}.{name} 必须为正整数。")
    if llm["context_tokens"] <= llm["max_output_tokens"] + 512:
        raise ValueError("上下文窗口必须为输入保留足够空间。")
    if not isinstance(tts.get("startup_text"), str):
        raise ValueError("tts.startup_text 必须为字符串，留空可关闭开场语音。")
    backend = tts.get("backend")
    if backend not in ("kokoro", "qwen3", "volcengine"):
        raise ValueError("tts.backend 仅支持 kokoro、qwen3 或 volcengine。")
    options = tts.get(backend)
    if not isinstance(options, dict):
        raise ValueError(f"tts.{backend} 必须为配置对象。")
    chunking = options.get("chunking")
    if not isinstance(chunking, dict):
        raise ValueError(f"tts.{backend}.chunking 必须为配置对象。")
    for name in ("first_min_chars", "second_min_chars", "later_min_chars"):
        value = chunking.get(name)
        if type(value) is not int or not 1 <= value <= tts["chunk_chars"]:
            raise ValueError(
                f"tts.{backend}.chunking.{name} 必须为不超过 tts.chunk_chars 的正整数。"
            )
    if backend == "kokoro":
        if (
            not isinstance(options.get("model_dir"), str)
            or not options["model_dir"].strip()
        ):
            raise ValueError("tts.kokoro.model_dir 必须为非空目录路径。")
        if type(options.get("threads")) is not int or options["threads"] <= 0:
            raise ValueError("tts.kokoro.threads 必须为正整数。")
        if (
            type(options.get("speaker_id")) is not int
            or not 0 <= options["speaker_id"] <= 102
        ):
            raise ValueError("tts.kokoro.speaker_id 范围是 0～102。")
        speed = options.get("speed")
        if (
            type(speed) not in (int, float)
            or not math.isfinite(speed)
            or not 0 < speed <= 3
        ):
            raise ValueError("tts.kokoro.speed 必须大于 0 且不超过 3。")
    elif backend == "qwen3":
        for name in ("model", "speaker"):
            if not isinstance(options.get(name), str) or not options[name].strip():
                raise ValueError(f"tts.qwen3.{name} 必须为非空字符串。")
    else:
        for name in ("voice_id", "api_key_env", "language_code"):
            if not isinstance(options.get(name), str) or not options[name].strip():
                raise ValueError(f"tts.volcengine.{name} 必须为非空字符串。")
        if type(options.get("sample_rate")) is not int or options[
            "sample_rate"
        ] not in (8000, 16000, 22050, 24000, 32000, 44100, 48000):
            raise ValueError("tts.volcengine.sample_rate 不是支持的采样率。")
        timeout = options.get("timeout_seconds")
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("tts.volcengine.timeout_seconds 必须为有限正数。")
        voice = options.get("voice_settings")
        if not isinstance(voice, dict):
            raise ValueError("tts.volcengine.voice_settings 必须为配置对象。")
        for name in ("speed", "volume"):
            value = voice.get(name)
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not 0.5 <= value <= 2
            ):
                raise ValueError(
                    f"tts.volcengine.voice_settings.{name} 范围是 0.5～2。"
                )
        if type(voice.get("pitch")) is not int or not -12 <= voice["pitch"] <= 12:
            raise ValueError(
                "tts.volcengine.voice_settings.pitch 必须为 -12～12 的整数。"
            )
    validate_voice_config(config)
    return config
