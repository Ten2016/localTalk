# LocalTalk · 本地语音助手

**让本地大模型开口说话。**

LocalTalk 将 Ollama 与中文语音合成连接起来，在自己的电脑上持续对话、朗读回答。默认使用本地 Qwen3-TTS，也可选择 CPU 上的 Kokoro，或火山 Seed-TTS 3.0 HTTP 流式语音合成。

回答流式显示，按句分段合成并顺序播放，无需等整篇回答结束。相同文本和声音设置优先复用本地音频，减少重复合成与云端调用。

文本收到即显示，音频独立排队播放。支持键盘与本地语音输入、多轮对话、音色配置、旧历史裁剪，以及最近使用的 1000 段音频缓存。语音模式使用 CPU 上的 Qwen3-ASR INT8 和 Silero VAD 6.3，说完停顿后自动回答；尚不支持语音打断和 STM32/ESP32 接入。

## 快速开始

使用 **Windows 10 22H2 或更新版本**、**64 位 Python 3.12**、正常的声音输出设备和已启动的 **Ollama**。默认 Qwen 后端还需要支持 CUDA 的 NVIDIA 显卡与兼容驱动；Kokoro 在 CPU 上合成；火山后端需要网络、API Key 和有权限的音色，无需本地 TTS 权重。各后端通过 `config.json` 切换，部署方式见 [TTS 说明](docs/tts.md)。

沿用已有的上级目录，模型、环境和输出均放在代码仓库外：

```text
H:/tts/
├── .venv/
├── kokoro-multi-lang-v1_1/
├── Qwen3-TTS-12Hz-0.6B-CustomVoice/
├── sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25/
├── silero-vad-v6.3/
├── tts-cache/
└── localTalk/
    ├── chat_tts.py
    ├── config.json
    ├── requirements.txt
    ├── localtalk/
    ├── scripts/
    │   ├── check_env.py
    │   └── benchmark_tts.py
    └── docs/
```

模型和输出目录都由 `config.json` 指定，支持绝对路径；相对路径以 `chat_tts.py` 所在目录为基准。Ollama 已下载的对话模型仍由 Ollama 管理，无需搬入仓库或重复下载。

首次获取项目，可在 `H:\tts` 中执行 `git clone https://github.com/Ten2016/localTalk.git`。已有仓库按下方[更新项目](#更新项目)操作，尤其是从 0.1.0 更新时先备份旧配置。

### 1. 检查已有环境并补齐依赖

以下命令均在 `localTalk` 项目根目录的 PowerShell 中执行：

```powershell
..\.venv\Scripts\python.exe --version
```

应显示 Python 3.12。环境尚未创建时，按[统一环境说明](docs/tts.md#统一环境)在上级目录创建 `.venv`；已有 3.12 环境直接复用，不再次创建。该说明也包含其他 Python 版本的依赖限制。

已有兼容环境时直接补齐依赖，不创建第二个环境：

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

依赖文件已指定 CUDA 12.8 版 PyTorch，包含本地与云端 TTS 后端、模型下载和静态检查所需依赖。准备好模型后用下方环境检查脚本统一确认；安装报错时也可运行脚本收集当前状态。尚未提供完整的传递依赖锁文件。

### 2. 核对配置及模型

直接修改仓库中的 `config.json`，无需复制模板：

| 参数 | 默认值 |
| --- | --- |
| `tts.backend` | `qwen3`，可切换为 `kokoro` 或 `volcengine` |
| `tts.kokoro.model_dir` | `../kokoro-multi-lang-v1_1` |
| `tts.qwen3.model` | `../Qwen3-TTS-12Hz-0.6B-CustomVoice` |
| `input.mode` | `keyboard`，准备模型后可改为 `voice` |
| `tts.audio_output_dir` | `../tts-cache` |

配置中每个分组的 `desc` 集中说明参数用途、可选值及试听链接；修改分组内的实际字段才会改变设置。模型已经下载时不需要重复下载；准备或迁移模型见 [TTS 部署说明](docs/tts.md#模型目录)。火山只需配置 `tts.volcengine` 和密钥环境变量，见[接入步骤](docs/tts.md#火山-seed-tts-30-http-流式)。

首次使用默认 Qwen 配置、尚未下载模型时，在项目根目录执行：

```powershell
..\.venv\Scripts\python.exe -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice', local_dir='../Qwen3-TTS-12Hz-0.6B-CustomVoice')"
```

确认 `ollama list` 中有配置指定的模型。仅在尚未下载默认对话模型时执行 `ollama pull qwen3.5:4b-q4_K_M`。

使用语音输入时，先按[本地语音输入](docs/asr.md)准备仓库外的 ASR、VAD 模型，再运行 `..\.venv\Scripts\python.exe -m scripts.check_env --voice`；只用键盘无需准备这两份模型。

### 3. 检查并启动

先运行环境检查：

```powershell
..\.venv\Scripts\python.exe -m scripts.check_env
```

脚本按 `config.json` 中的后端检查 Python 环境、依赖版本与兼容性、模型关键文件、TTS 导入以及 Ollama 服务和模型；Qwen 还会显示显卡、驱动、显存并执行一次小规模 CUDA BF16 运算。火山检查密钥环境变量、HTTP 依赖和 MP3 解码支持，不连接合成接口。逐项显示“通过 / 注意 / 失败”和处理建议，最后汇总。

检查不安装依赖、不下载或加载模型、不合成或播放音频。具体检查边界见 [环境检查说明](docs/tts.md#检查-gpu-与依赖)。处理失败项后启动：

```powershell
..\.venv\Scripts\python.exe .\chat_tts.py
```

保持 Ollama 服务运行，不需要另外打开 `ollama run` 会话。加载 TTS 后默认播放开场语音，再输入“你好”确认对话和声音；开场语可通过 `tts.startup_text` 修改，空字符串关闭。

如果 Qwen 合成速度跟不上播放，可运行独立的 [TTS 性能测试](docs/benchmark.md)，比较单句与两句批量生成，以及 Ollama 卸载、驻留和生成时的差异；报告保存在仓库外。

## 更新项目

停止正在运行的 LocalTalk，以下命令在项目根目录执行。

从 0.2.0 更新时，`config.json` 已改为 `llm`、`tts` 分组，原有音色、路径等自定义值需按[配置说明](docs/usage.md#配置)填入对应子组；旧平铺字段不再读取。先将旧配置备份到仓库外，不用旧文件整体覆盖新版。

**从 0.1.0 首次更新到 0.2.0 时，先备份旧配置再拉取。** 旧版 `config.json` 被 Git 忽略，新版开始跟踪该文件，拉取时旧文件可能被覆盖。备份放在仓库上级，不作为第二份运行配置：

```powershell
if (Test-Path .\config.json) {
    Copy-Item .\config.json ("..\localTalk-config-backup-{0}.json" -f (Get-Date -Format "yyyyMMdd-HHmmss-fff"))
}
```

拉取更新并安装依赖：

```powershell
git pull --ff-only
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

更新后核对新的 `config.json`，只把需要保留的音色、路径等设置填回，不用旧文件整份覆盖新版。默认后端已切换为 Qwen，首次启动前需完成上方模型下载；继续使用已有 Kokoro 时将 `tts.backend` 改为 `kokoro`。

准备好后启动：

```powershell
..\.venv\Scripts\python.exe .\chat_tts.py
```

后续更新前可用 `git status --short` 查看本地改动。若 Git 因配置或其他文件改动拒绝拉取，先保留并合并这些改动，不使用强制覆盖。环境、模型和音频位于仓库外，无需随代码更新重新创建或下载。

## 基本操作

| 操作 | 效果 |
| --- | --- |
| 输入问题并回车 | 流式显示回答，并分段朗读 |
| `/voice` | 加载本地模型，进入连续语音对话 |
| 语音监听或识别时 `Ctrl+C` | 取消本次输入，返回键盘 |
| `/clear` | 清空当前对话历史 |
| `/quit` | 退出程序 |
| 修改 `tts.kokoro.speaker_id` | 选择 Kokoro 音色，重启生效 |
| 修改 `tts.qwen3.speaker` | 选择 Qwen 音色，重启生效 |
| 修改 `tts.kokoro.speed` | 调整 Kokoro 语速，`1.0` 为默认，大于 1 更快 |
| 打开 `tts.audio_output_dir` 指定的目录 | 回听最近使用的 1000 个缓存片段 |
| 修改 `tts.backend` | 重启后切换 `kokoro`、`qwen3` 或 `volcengine` |

中文女声可先对比 `3` 和 `40`，男声可试 `58` 和 `59`；这些是试听起点，不代表质量排名。完整参数、音色对应关系和排障说明见[使用说明](docs/usage.md)。

Qwen 中文声音可先对比 Serena、Vivian 和 Uncle_Fu，通过 `tts.qwen3.speaker` 选择；Kokoro 使用 `tts.kokoro.speaker_id`。各后端共用上级目录的 `.venv`，修改配置后用同一条命令重启。详细部署与比较见 [TTS 说明](docs/tts.md)。

## 使用须知

- 当前需等本轮播放结束后再输入下一问；语音模式在回答期间关闭麦克风，尚不支持语音打断或回声消除；退出时会等待正在合成或播放的片段完成。
- 历史只保存在内存中，退出后清空；长对话按保守估算裁剪，不是长期记忆。
- 首段合成后即可播放，但短片段之间仍可能有停顿；分段播放不保证减少总合成时间。
- `config.json` 随仓库管理；模型、虚拟环境和生成音频在 Git 忽略范围内。音频可能包含对话内容，请勿直接作为问题附件公开。
- 本地 LLM 和 TTS 权重需单独下载，分别遵循其原始许可；本项目不会校验或纠正模型回答。
- 选择火山时，未命中缓存的助手回答片段及开场语会发送到云端，调用可能产生费用；API Key 仅从环境变量读取，不写入仓库。
- Kokoro 分段播放已有 Windows 使用反馈；ASR/VAD、当前分层配置与火山接入只完成静态检查，仍需在目标电脑上验证。

## 相关项目

[Ollama](https://github.com/ollama/ollama) 提供本地模型服务，[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) 提供 GPU 语音合成，[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 提供 CPU 语音推理，[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh) 提供中文语音模型。

项目代码采用 [MIT 许可证](LICENSE)，第三方依赖和模型分别遵循其原始许可。

[使用说明](docs/usage.md) · [本地语音输入](docs/asr.md) · [更新日志](CHANGELOG.md) · [贡献指南](CONTRIBUTING.md) · [MIT 许可证](LICENSE)
