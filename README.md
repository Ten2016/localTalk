# LocalTalk · 本地语音助手

**让本地大模型开口说话。**

LocalTalk 将 Ollama 与 Kokoro 中文语音合成连接起来，在自己的电脑上持续对话、朗读回答。大模型可以使用 GPU，语音合成运行在 CPU 上，无需云端语音 API。

回答流式显示，首段遇到合适标点就开始合成；播放期间继续准备下一段，不必等整篇回答合成完才听到声音。

支持多轮对话、中文音色与语速配置、旧历史裁剪，以及本轮音频保存。当前是 **Windows 键盘对话原型**；麦克风、ASR、VAD 和 STM32/ESP32 接入尚未实现。

## 快速开始

需要 **Windows 10 22H2 或更新版本**、**64 位 Python 3.15**、正常工作的声音输出设备，以及已启动的 **Ollama**。以下命令在项目根目录的 PowerShell 中执行。

### 1. 安装 Python 依赖

下载项目源码，进入项目根目录，然后执行：

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

已有可用的虚拟环境时，可以直接用其中的 Python，无需重复创建。Python 3.15 是当前实验使用的版本；其他版本尚未验证。依赖版本范围见 `requirements.txt`，尚未提供完整环境锁文件。

### 2. 准备模型

下载默认对话模型；如果已经安装，可跳过：

```powershell
ollama pull qwen3.5:4b-q4_K_M
```

下载并解压 Kokoro 中文语音模型：

```powershell
New-Item -ItemType Directory -Force models | Out-Null
curl.exe -L --fail --retry 3 -C - -o models/kokoro-multi-lang-v1_1.tar.bz2 "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_1.tar.bz2"
.\.venv\Scripts\python.exe -c "import tarfile; tarfile.open('models/kokoro-multi-lang-v1_1.tar.bz2').extractall('models', filter='data')"
```

请在下载成功后执行解压；下载中断可以重新执行同一条 `curl.exe` 命令续传。已有解压模型时无需重复下载，在下一步填入原目录即可。

### 3. 配置并启动

首次使用时复制配置；已有 `config.json` 时跳过复制，避免覆盖个人设置：

```powershell
Copy-Item config.example.json config.json
```

打开 `config.json`，确认 `model` 与 `ollama list` 中的名称一致，`tts_model_dir` 指向模型目录。默认路径为项目下的 `models/kokoro-multi-lang-v1_1`；Windows 绝对路径使用正斜杠，例如 `D:/models/kokoro-multi-lang-v1_1`。

```powershell
.\.venv\Scripts\python.exe .\chat_tts.py
```

不需要另外打开 `ollama run` 会话。先输入“你好”确认声音，再尝试长故事和连续追问。

## 基本操作

| 操作 | 效果 |
| --- | --- |
| 输入问题并回车 | 流式显示回答，并分段朗读 |
| `/clear` | 清空当前对话历史 |
| `/quit` | 退出程序 |
| 修改 `speaker_id` | 选择音色，重启生效 |
| 修改 `speech_speed` | 调整语速，`1.0` 为默认，大于 1 更快 |
| 打开 `output/last_reply.wav` | 回听最新一轮已播放的音频 |

中文女声可先对比 `3` 和 `40`，男声可试 `58` 和 `59`；这些是试听起点，不代表质量排名。完整参数、音色对应关系和排障说明见[使用说明](docs/usage.md)。

## 使用须知

- 当前需等本轮播放结束后再输入下一问，尚不支持语音打断；退出时会等待正在合成或播放的片段完成。
- 历史只保存在内存中，退出后清空；长对话按保守估算裁剪，不是长期记忆。
- 首段合成后即可播放，但短片段之间仍可能有停顿；分段播放不保证减少总合成时间。
- `config.json`、模型、虚拟环境和生成音频均在 Git 忽略范围内。音频可能包含对话内容，请勿直接作为问题附件公开。
- LLM 和 TTS 的模型权重需单独下载，分别遵循其原始许可；本项目不会校验或纠正模型回答。
- 当前分段版本只完成本地静态检查，尚未完成目标 Windows 环境的功能验收。

## 相关项目

[Ollama](https://github.com/ollama/ollama) 提供本地模型服务，[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 提供 CPU 语音推理，[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh) 提供中文语音模型。

项目代码采用 [MIT 许可证](LICENSE)，第三方依赖和模型分别遵循其原始许可。

[使用说明](docs/usage.md) · [更新日志](CHANGELOG.md) · [贡献指南](CONTRIBUTING.md) · [MIT 许可证](LICENSE)
