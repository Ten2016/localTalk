from pathlib import Path

from .config import BASE


def model_file(config):
    path = Path(config["model_path"]).expanduser()
    return path if path.is_absolute() else BASE / path


class SileroVAD:
    sample_rate = 16000
    frame_samples = 512

    def __init__(self, config):
        path = model_file(config)
        if not path.is_file():
            raise FileNotFoundError(f"缺少 Silero 6.3 模型：{path}，见 docs/asr.md。")
        import numpy as np
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.np = np
        self.threshold = config["threshold"]
        self.reset()

    def reset(self):
        self.state = self.np.zeros((2, 1, 128), dtype="float32")
        self.context = self.np.zeros((1, 64), dtype="float32")

    def probability(self, frame):
        if frame.shape != (self.frame_samples,):
            raise ValueError("Silero 16kHz 输入必须为单声道 512 采样点。")
        # Silero 的状态和 64 点上下文跨帧保留，每轮监听重新初始化。
        samples = self.np.concatenate((self.context, frame.reshape(1, -1)), axis=1)
        output, self.state = self.session.run(
            None,
            {
                "input": samples,
                "state": self.state,
                "sr": self.np.array(self.sample_rate, dtype="int64"),
            },
        )
        self.context = samples[:, -64:].copy()
        return float(output[0, 0])
