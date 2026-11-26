from pathlib import Path

from ..config import BASE


def resolve_qwen_model(name):
    model_path = Path(name).expanduser()
    local_path = model_path.is_absolute() or name.startswith((".", "~")) or "\\" in name
    if not model_path.is_absolute():
        model_path = BASE / model_path
    if local_path and not model_path.is_dir():
        raise FileNotFoundError(
            f"找不到 Qwen 模型目录：{model_path}。请按 docs/tts.md 下载模型，"
            "或修改 config.json 中的 tts.qwen3.model。"
        )
    return str(model_path) if model_path.exists() else name


class QwenTTS:
    def __init__(self, config):
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError as exc:
            raise RuntimeError(
                "Qwen3 依赖未安装完整，请使用统一环境安装 requirements.txt，步骤见 docs/tts.md。"
            ) from exc
        if not torch.cuda.is_available():
            raise RuntimeError(
                "Qwen3 GPU 后端需要可用的 CUDA PyTorch，请检查安装及驱动。"
            )
        model = resolve_qwen_model(config["model"])
        self.model = Qwen3TTSModel.from_pretrained(
            model,
            device_map="cuda:0",
            dtype=torch.bfloat16,
            attn_implementation="sdpa",
        )
        talker = self.model.model.talker
        if talker.generation_config.pad_token_id is None:
            # 沿用生成库以音频结束符填充的默认行为，避免每段合成重复提示。
            talker.generation_config.pad_token_id = talker.config.codec_eos_token_id
        speakers = self.model.get_supported_speakers() or []
        if config["speaker"].lower() not in [speaker.lower() for speaker in speakers]:
            raise ValueError(f"Qwen3 音色不受支持，可用音色：{', '.join(speakers)}")
        self.speaker = config["speaker"]
        self.cache_identity = {
            "backend": "qwen3",
            "model": Path(model).name,
            "voice": self.speaker.lower(),
        }

    def generate(self, text):
        waveforms, sample_rate = self.model.generate_custom_voice(
            text=text,
            language="Chinese",
            speaker=self.speaker,
        )
        if len(waveforms) != 1:
            raise RuntimeError("Qwen3 没有返回单段音频。")
        return waveforms[0], sample_rate
