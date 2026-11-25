def create_tts(config):
    config = config["tts"]
    if config["backend"] == "volcengine":
        from .volcengine import VolcengineTTS

        return VolcengineTTS(config["volcengine"])
    if config["backend"] == "qwen3":
        from .qwen import QwenTTS

        return QwenTTS(config["qwen3"])
    if config["backend"] == "kokoro":
        from .kokoro import KokoroTTS

        return KokoroTTS(config["kokoro"])
    raise ValueError("tts.backend 仅支持 kokoro、qwen3 或 volcengine。")
