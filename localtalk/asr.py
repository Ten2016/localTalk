from pathlib import Path

from .config import BASE


MODEL_FILES = (
    "conv_frontend.onnx",
    "encoder.int8.onnx",
    "decoder.int8.onnx",
    "tokenizer/vocab.json",
    "tokenizer/merges.txt",
    "tokenizer/tokenizer_config.json",
)


def model_files(config):
    directory = Path(config["model_dir"]).expanduser()
    if not directory.is_absolute():
        directory = BASE / directory
    return {name: directory / name for name in MODEL_FILES}


class QwenASR:
    def __init__(self, config):
        files = model_files(config)
        missing = [str(path) for path in files.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                f"缺少 ASR 模型文件：{', '.join(missing)}。准备步骤见 docs/asr.md。"
            )
        import sherpa_onnx

        factory = getattr(sherpa_onnx.OfflineRecognizer, "from_qwen3_asr", None)
        if factory is None:
            raise RuntimeError(
                "当前 sherpa-onnx 不支持 Qwen3-ASR，请安装 requirements.txt。"
            )
        self.model = factory(
            conv_frontend=str(files["conv_frontend.onnx"]),
            encoder=str(files["encoder.int8.onnx"]),
            decoder=str(files["decoder.int8.onnx"]),
            tokenizer=str(files["tokenizer/vocab.json"].parent),
            provider="cpu",
            num_threads=config["threads"],
            sample_rate=16000,
            feature_dim=128,
            max_total_len=2048,
            max_new_tokens=512,
        )
        self.language = config["language"].strip()

    def transcribe(self, samples):
        stream = self.model.create_stream()
        if self.language:
            stream.set_option("language", self.language)
        stream.accept_waveform(16000, samples)
        self.model.decode_stream(stream)
        result = stream.result
        text = result.text.strip()
        if "<|" in text or "<asr_text>" in text or len(result.tokens) >= 512:
            raise RuntimeError("识别结果包含控制标记或达到输出上限，本轮没有提交。")
        if not text:
            raise RuntimeError("未识别到文字，本轮没有提交，请重新说话或使用键盘。")
        return text
