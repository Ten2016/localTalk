from pathlib import Path

from ..config import BASE


MODEL_FILES = (
    "model.onnx",
    "voices.bin",
    "tokens.txt",
    "lexicon-us-en.txt",
    "lexicon-zh.txt",
)


class KokoroTTS:
    def __init__(self, config):
        import sherpa_onnx

        model_dir = Path(config["model_dir"]).expanduser()
        if not model_dir.is_absolute():
            model_dir = BASE / model_dir

        def path(name):
            result = model_dir / name
            if not result.exists():
                raise FileNotFoundError(f"缺少 TTS 模型文件或目录：{result}")
            return str(result)

        files = {name: path(name) for name in MODEL_FILES}
        tts_config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                    model=files["model.onnx"],
                    voices=files["voices.bin"],
                    tokens=files["tokens.txt"],
                    data_dir=path("espeak-ng-data"),
                    lexicon=",".join(
                        [files["lexicon-us-en.txt"], files["lexicon-zh.txt"]]
                    ),
                ),
                provider="cpu",
                num_threads=config["threads"],
            ),
            max_num_sentences=1,
        )
        if not tts_config.validate():
            raise ValueError("TTS 配置校验失败。")
        self.model = sherpa_onnx.OfflineTts(tts_config)
        self.speaker = config["speaker_id"]
        self.speed = config["speed"]
        self.cache_identity = {
            "backend": "kokoro",
            "model": str(model_dir.resolve()),
            "speaker_id": self.speaker,
            "speed": self.speed,
        }

    def generate(self, text):
        audio = self.model.generate(text=text, sid=self.speaker, speed=self.speed)
        return audio.samples, audio.sample_rate
