def create_tts(config):
    if config["tts_backend"] == "qwen3":
        from .qwen import QwenTTS

        return QwenTTS(config)
    if config["tts_backend"] == "kokoro":
        from .kokoro import KokoroTTS

        return KokoroTTS(config)
    raise ValueError("tts_backend 仅支持 kokoro 或 qwen3。")
