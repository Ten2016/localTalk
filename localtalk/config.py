import json
from pathlib import Path

from .text import MIN_CHUNK_CHARS


BASE = Path(__file__).resolve().parent.parent


def load_config():
    config_path = BASE / "config.json"
    if not config_path.exists():
        raise FileNotFoundError("缺少 config.json，请从仓库恢复该文件并配置模型目录。")
    with config_path.open(encoding="utf-8-sig") as handle:
        config = json.load(handle)
    config.setdefault("tts_backend", "kokoro")
    config.setdefault("qwen_model", "../Qwen3-TTS-12Hz-0.6B-CustomVoice")
    config.setdefault("qwen_speaker", "Serena")
    config.setdefault("audio_output_dir", "../output/segments")
    if (
        not isinstance(config["audio_output_dir"], str)
        or not config["audio_output_dir"].strip()
    ):
        raise ValueError("audio_output_dir 必须为非空目录路径。")
    if config["tts_backend"] not in ("kokoro", "qwen3"):
        raise ValueError("tts_backend 仅支持 kokoro 或 qwen3。")
    config.setdefault("startup_text", "你好，我在，请问有什么可以帮你？")
    if not isinstance(config["startup_text"], str):
        raise ValueError("startup_text 必须为字符串，留空可关闭开场语音。")
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
    if min(config["first_chunk_chars"], config["chunk_chars"]) < MIN_CHUNK_CHARS:
        raise ValueError(f"文本分段上限至少为 {MIN_CHUNK_CHARS} 个字符。")
    if not 0 < config["speech_speed"] <= 3:
        raise ValueError("speech_speed 必须大于 0 且不超过 3。")
    if config["tts_backend"] == "kokoro":
        if (
            type(config["speaker_id"]) is not int
            or not 0 <= config["speaker_id"] <= 102
        ):
            raise ValueError("Kokoro v1.1 的 speaker_id 范围是 0～102。")
    else:
        if config["speech_speed"] != 1.0:
            raise ValueError(
                "当前 Qwen3 接入不支持数值语速控制，请将 speech_speed 设为 1.0。"
            )
        for name in ("qwen_model", "qwen_speaker"):
            if not isinstance(config[name], str) or not config[name].strip():
                raise ValueError(f"{name} 必须为非空字符串。")
    return config
