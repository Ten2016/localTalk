import base64
import io
import json
import os
from urllib.parse import quote
from uuid import uuid4


class VolcengineTTS:
    def __init__(self, config):
        import requests

        self.options = config
        self.api_key = os.environ.get(config["api_key_env"], "").strip()
        if not self.api_key:
            raise ValueError(
                f"请先设置环境变量 {config['api_key_env']}，不要将密钥写入配置文件。"
            )
        voice_id = quote(config["voice_id"], safe="")
        self.url = (
            "https://voice.cn-beijing.volces.com/api/v3/text-to-speech/"
            f"{voice_id}/streaming"
        )
        self.parameters = {
            "model_id": "doubao-seed-tts-3.0",
            "language_code": config["language_code"],
            "output_format": {
                "format": "mp3",
                "sample_rate": config["sample_rate"],
                "bit_rate": 64000,
            },
            "voice_settings": config["voice_settings"],
            "text_normalization": True,
            "enable_markdown_filter": False,
            "enable_subtitle": False,
        }
        self.cache_identity = {
            "backend": "volcengine",
            "model_id": self.parameters["model_id"],
            "voice_id": config["voice_id"],
            "language_code": config["language_code"],
            "sample_rate": config["sample_rate"],
            "voice_settings": config["voice_settings"],
        }
        self.session = requests.Session()

    def close(self):
        self.session.close()

    def generate(self, text):
        import requests
        import soundfile as sf

        if len(text) > 10000:
            raise ValueError(
                "火山单次合成文本不能超过 10000 字符，请调小分段上限或开场语。"
            )
        request_id = str(uuid4())
        audio = bytearray()
        ready = completed = False
        try:
            with self.session.post(
                self.url,
                headers={"X-Api-Key": self.api_key, "X-Request-Id": request_id},
                json={"text": text, **self.parameters},
                stream=True,
                timeout=(10, self.options["timeout_seconds"]),
                allow_redirects=False,
            ) as response:
                if not response.ok or response.is_redirect:
                    try:
                        data = response.json()
                    except ValueError:
                        data = {}
                    error = data.get("error", {}) if isinstance(data, dict) else {}
                    raise RuntimeError(
                        f"火山语音 HTTP {response.status_code}，"
                        f"错误码={error.get('code', 'unknown')}；request_id={request_id}。"
                    )
                for line in response.iter_lines(chunk_size=1024):
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise RuntimeError("火山语音返回的事件格式不正确。")
                    kind = event.get("event")
                    if kind == "error":
                        error = event.get("error", {})
                        raise RuntimeError(
                            f"火山语音错误 {error.get('code', 'unknown')}；"
                            f"request_id={error.get('request_id') or request_id}。"
                        )
                    if completed:
                        raise RuntimeError("火山语音在结束标记后继续返回了事件。")
                    if kind == "ready":
                        ready = True
                    elif not ready:
                        raise RuntimeError("火山语音未返回 ready，请求未就绪。")
                    elif kind == "audio":
                        audio.extend(base64.b64decode(event["audio"], validate=True))
                    elif kind == "final":
                        if (
                            event.get("is_final") is not True
                            or event.get("reason") != "TTS_STREAM_FINAL_REASON_CLOSED"
                        ):
                            raise RuntimeError("火山语音返回了未知的结束标记。")
                        completed = True
        except requests.RequestException:
            raise RuntimeError(
                f"火山语音请求失败或超时；request_id={request_id}。"
            ) from None
        if not completed:
            raise RuntimeError(
                f"火山语音连接中断，音频未收齐；request_id={request_id}。"
            )
        if not audio:
            raise RuntimeError("火山语音未返回该段文本的音频。")
        samples, sample_rate = sf.read(io.BytesIO(audio), dtype="float32")
        if sample_rate != self.options["sample_rate"]:
            raise RuntimeError("火山语音返回的采样率与配置不一致。")
        return samples, sample_rate
