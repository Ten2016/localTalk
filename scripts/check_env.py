import json
import os
import platform
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import ProxyHandler, build_opener

from localtalk import VERSION
from localtalk.config import BASE, load_config
from localtalk.tts.kokoro import MODEL_FILES
from localtalk.tts.qwen import resolve_qwen_model


class CheckWarning(Exception):
    pass


class Report:
    def __init__(self):
        self.errors = 0
        self.warnings = 0

    def show(self, status, title, detail):
        self.errors += status == "失败"
        self.warnings += status == "注意"
        print(f"\n[{status}] {title}", flush=True)
        print(detail, flush=True)

    def check(self, title, action, hint, describe=str):
        print(f"\n正在检查：{title}……", flush=True)
        try:
            result = action()
            detail = describe(result)
        except CheckWarning as exc:
            self.show("注意", title, str(exc))
            return None
        except Exception as exc:
            self.show("失败", title, f"{exc}\n处理建议：{hint}")
            return None
        self.show("通过", title, detail)
        return result


def command(args):
    result = subprocess.run(
        args,
        cwd=BASE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part)
    if result.returncode:
        raise RuntimeError(f"退出码 {result.returncode}\n{output[-6000:]}")
    return output[-6000:] or "命令执行成功。"


def check_requirements(backend):
    required = {"soundfile", "requests", "packaging", "ruff"} | {
        "kokoro": {"sherpa-onnx"},
        "qwen3": {"qwen-tts", "torch", "torchaudio", "modelscope"},
        "volcengine": set(),
    }[backend]
    return command(
        [
            sys.executable,
            "-c",
            """
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from packaging.requirements import Requirement
import json
import sys

required = set(json.loads(sys.argv[1]))
failed = False
for line in Path('requirements.txt').read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if not line or line.startswith(('#', '--')):
        continue
    requirement = Requirement(line)
    if requirement.name.lower().replace('_', '-') not in required:
        continue
    try:
        installed = version(requirement.name)
    except PackageNotFoundError:
        print(f'{requirement.name}: 未安装')
        failed = True
        continue
    valid = requirement.specifier.contains(installed, prereleases=True)
    print(f'{requirement.name}: {installed}' + ('' if valid else f'，要求 {requirement.specifier}'))
    failed |= not valid
raise SystemExit(1 if failed else 0)
""",
            json.dumps(sorted(required)),
        ]
    )


def check_volcengine(config):
    name = config["tts"]["volcengine"]["api_key_env"]
    if not os.environ.get(name, "").strip():
        raise ValueError(f"环境变量 {name} 未设置或为空。")
    return f"环境变量 {name} 已设置；未连接火山，不验证密钥、音色权限或余额。"


def check_model(config):
    config = config["tts"]
    if config["backend"] == "qwen3":
        directory = Path(resolve_qwen_model(config["qwen3"]["model"]))
        if not directory.is_dir():
            raise CheckWarning(
                "配置为在线模型 ID；未检查远程权重及缓存，请先下载到本地再检查。"
            )
        names = (
            "config.json",
            "tokenizer_config.json",
            "preprocessor_config.json",
            "vocab.json",
            "merges.txt",
            "speech_tokenizer/config.json",
        )
        missing = [name for name in names if not (directory / name).is_file()]
        for folder in (directory, directory / "speech_tokenizer"):
            if not any(folder.glob("*.safetensors")):
                missing.append(str(folder / "*.safetensors"))
    else:
        directory = Path(config["kokoro"]["model_dir"]).expanduser()
        if not directory.is_absolute():
            directory = BASE / directory
        missing = [name for name in MODEL_FILES if not (directory / name).is_file()]
        if not (directory / "espeak-ng-data").is_dir():
            missing.append("espeak-ng-data/")
    if missing:
        raise FileNotFoundError(f"目录：{directory}\n缺少：{', '.join(missing)}")
    return f"目录：{directory.resolve()}\n关键文件存在；未校验权重哈希或完整分片。"


def check_ollama(config):
    config = config["llm"]
    url = urlsplit(config["url"])
    if url.scheme not in ("http", "https") or not url.netloc:
        raise ValueError("llm.url 必须为有效的 HTTP/HTTPS 地址。")
    if not url.path.endswith("/api/chat"):
        raise ValueError("当前检查要求 llm.url 的路径以 /api/chat 结尾。")
    tags_url = urlunsplit(url._replace(path=url.path[:-4] + "tags", fragment=""))
    opener = (
        build_opener(ProxyHandler({}))
        if url.hostname in ("127.0.0.1", "localhost", "::1")
        else build_opener()
    )
    with opener.open(tags_url, timeout=5) as response:
        models = json.load(response)["models"]

    def normalize(name):
        return name if ":" in name.rsplit("/", 1)[-1] else name + ":latest"

    names = [item["name"] for item in models]
    if normalize(config["model"]) not in {normalize(name) for name in names}:
        raise ValueError(
            f"服务可访问，但未找到配置的模型 {config['model']}。\n"
            f"已有模型：{', '.join(names) or '无'}"
        )
    return f"服务可访问，已安装 {config['model']}；未加载或运行对话模型。"


def main():
    print(f"LocalTalk {VERSION} · 环境检查", flush=True)
    print(f"解释器：{sys.executable}\n基础环境：{sys.base_prefix}")
    report = Report()
    report.show(
        "通过" if os.name == "nt" else "失败",
        "操作系统",
        f"{platform.platform()}；当前音频播放需要 Windows。",
    )
    report.show(
        "通过" if struct.calcsize("P") == 8 else "失败",
        "解释器位数",
        f"{struct.calcsize('P') * 8} 位；项目需要 64 位 Python。",
    )
    report.show(
        "通过" if sys.version_info[:2] == (3, 12) else "注意",
        "Python 版本",
        f"{platform.python_version()}；当前依赖组合按 Python 3.12 配置。",
    )
    expected = (BASE.parent / ".venv").resolve()
    report.show(
        "通过" if Path(sys.prefix).resolve() == expected else "注意",
        "虚拟环境",
        f"当前：{sys.prefix}\n预期：{expected}\n建议使用 ..\\.venv\\Scripts\\python.exe。",
    )
    install_hint = "使用 ..\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt 安装依赖。"
    report.check(
        "依赖兼容性",
        lambda: command([sys.executable, "-m", "pip", "check"]),
        install_hint,
    )
    config = report.check(
        "配置",
        load_config,
        "检查 config.json 的字段、类型和取值。",
        describe=lambda value: (
            f"当前后端：{value['tts']['backend']}；对话模型：{value['llm']['model']}"
        ),
    )
    if config is not None:
        report.check(
            "当前后端依赖版本",
            lambda: check_requirements(config["tts"]["backend"]),
            install_hint,
        )
        if config["tts"]["backend"] != "volcengine":
            report.check(
                "TTS 模型文件",
                lambda: check_model(config),
                "按 docs/tts.md 下载模型并核对配置中的路径。",
            )
        if config["tts"]["backend"] == "qwen3":
            smi = shutil.which("nvidia-smi")
            if smi:
                report.check(
                    "显卡 / 驱动 / 显存（总量、已用、剩余，单位 MiB）",
                    lambda: command(
                        [
                            smi,
                            "--query-gpu=name,driver_version,memory.total,memory.used,memory.free",
                            "--format=csv,noheader,nounits",
                        ]
                    ),
                    "检查 NVIDIA 驱动和 nvidia-smi 输出。",
                )
            else:
                report.show(
                    "注意", "显卡状态", "未找到 nvidia-smi；继续以 CUDA 运算检查为准。"
                )
            report.check(
                "CUDA BF16 运算",
                lambda: command(
                    [
                        sys.executable,
                        "-c",
                        """
import torch

print('PyTorch:', torch.__version__, 'CUDA:', torch.version.cuda)
if not torch.cuda.is_available():
    raise RuntimeError('CUDA 不可用')
print('显卡:', torch.cuda.get_device_name(0))
x = torch.ones((32, 32), device='cuda:0', dtype=torch.bfloat16)
value = (x @ x)[0, 0].item()
if value != 32.0:
    raise RuntimeError(f'BF16 运算结果异常：{value}，预期 32.0')
print('BF16 运算结果:', value)
""",
                    ]
                ),
                "核对 CUDA 版 PyTorch、NVIDIA 驱动及完整报错，见 docs/tts.md。",
            )
            report.check(
                "Qwen 与音频依赖导入",
                lambda: command(
                    [
                        sys.executable,
                        "-c",
                        "from qwen_tts import Qwen3TTSModel; import soundfile, requests; print('Qwen 和音频依赖导入成功')",
                    ]
                ),
                install_hint,
            )
        elif config["tts"]["backend"] == "kokoro":
            report.check(
                "Kokoro 与音频依赖导入",
                lambda: command(
                    [
                        sys.executable,
                        "-c",
                        "import sherpa_onnx, soundfile, requests; print('Kokoro 和音频依赖导入成功')",
                    ]
                ),
                install_hint,
            )
        else:
            report.check(
                "火山凭据配置",
                lambda: check_volcengine(config),
                "在启动 LocalTalk 的 PowerShell 中设置密钥环境变量，见 docs/tts.md。",
            )
            report.check(
                "HTTP 与 MP3 解码依赖",
                lambda: command(
                    [
                        sys.executable,
                        "-c",
                        "import soundfile as sf, requests; "
                        "assert 'MP3' in sf.available_formats(), '当前 libsndfile 不支持 MP3'; "
                        "print('HTTP 依赖和 MP3 格式支持可用')",
                    ]
                ),
                install_hint,
            )
        report.check(
            "Ollama 服务与模型",
            lambda: check_ollama(config),
            "启动 Ollama，检查 llm.url 和 ollama list；缺少模型时使用 ollama pull 下载。",
        )
    print(f"\n检查完成：{report.errors} 项失败，{report.warnings} 项需注意。")
    print(
        "此检查不合成或播放声音，也不调用火山接口；不证明模型文件完整、云端权限、音质或显存足够。"
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
