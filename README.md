# LocalTalk · 本地语音助手

**让本地大模型开口说话。**

LocalTalk 将 Ollama 与本地中文语音合成连接起来，在自己的电脑上持续对话、朗读回答。配置默认使用 GPU 上的 Qwen3-TTS，也可切换到 CPU 上的 Kokoro，无需云端语音 API。

回答流式显示，每段累计至少 20 个字符后在合适标点处分段合成，短句会与后文合并；回答结束时不足 20 字的尾段也会正常朗读。播放期间继续准备下一段，不必等整篇回答合成完才听到声音。

文本收到即显示，音频独立排队播放。支持多轮对话、音色配置、Kokoro 语速调整、旧历史裁剪，以及最近 100 段音频保存。当前是 **Windows 键盘对话原型**；麦克风、ASR、VAD 和 STM32/ESP32 接入尚未实现。

## 快速开始

使用 **Windows 10 22H2 或更新版本**、**64 位 Python 3.12**、正常的声音输出设备和已启动的 **Ollama**。默认 Qwen 后端还需要支持 CUDA 的 NVIDIA 显卡与兼容驱动；Kokoro 在 CPU 上合成。两者共用一个环境、一个 `requirements.txt`，通过 `config.json` 切换。

沿用已有的上级目录，模型、环境和输出均放在代码仓库外：

```text
H:/tts/
├── .venv/
├── kokoro-multi-lang-v1_1/
├── Qwen3-TTS-12Hz-0.6B-CustomVoice/
├── output/
│   └── segments/
└── localTalk/
    ├── chat_tts.py
    ├── check_env.py
    ├── config.json
    ├── requirements.txt
    ├── localtalk/
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

依赖文件已指定 CUDA 12.8 版 PyTorch，包含两个 TTS 后端、模型下载和静态检查所需依赖。准备好模型后用下方环境检查脚本统一确认；安装报错时也可运行脚本收集当前状态。尚未提供完整的传递依赖锁文件。

### 2. 核对配置及模型

直接修改仓库中的 `config.json`，无需复制模板：

| 参数 | 默认值 |
| --- | --- |
| `tts_backend` | `qwen3`，可切换为 `kokoro` |
| `tts_model_dir` | `../kokoro-multi-lang-v1_1` |
| `qwen_model` | `../Qwen3-TTS-12Hz-0.6B-CustomVoice` |
| `audio_output_dir` | `../output/segments` |

配置中的 `*_desc` 字段说明可选值、推荐音色及试听链接；修改对应的不带 `_desc` 的字段才会改变设置。模型已经下载时不需要重复下载；准备或迁移模型见 [TTS 部署说明](docs/tts.md#模型目录)。

首次使用默认 Qwen 配置、尚未下载模型时，在项目根目录执行：

```powershell
..\.venv\Scripts\python.exe -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice', local_dir='../Qwen3-TTS-12Hz-0.6B-CustomVoice')"
```

确认 `ollama list` 中有配置指定的模型。仅在尚未下载默认对话模型时执行 `ollama pull qwen3.5:4b-q4_K_M`。

### 3. 检查并启动

先运行环境检查：

```powershell
..\.venv\Scripts\python.exe .\check_env.py
```

脚本按 `config.json` 中的后端检查 Python 环境、依赖版本与兼容性、模型关键文件、TTS 导入以及 Ollama 服务和模型；Qwen 还会显示显卡、驱动、显存并执行一次小规模 CUDA BF16 运算。逐项显示“通过 / 注意 / 失败”和处理建议，最后汇总。缺少依赖时也能启动诊断；未下载模型时会报告缺少文件。

检查不安装依赖、不下载或加载模型、不合成或播放音频。具体检查边界见 [环境检查说明](docs/tts.md#检查-gpu-与依赖)。处理失败项后启动：

```powershell
..\.venv\Scripts\python.exe .\chat_tts.py
```

保持 Ollama 服务运行，不需要另外打开 `ollama run` 会话。加载 TTS 后默认播放开场语音，再输入“你好”确认对话和声音；开场语可通过 `startup_text` 修改，空字符串关闭。

如果 Qwen 合成速度跟不上播放，可运行独立的 [TTS 性能测试](docs/benchmark.md)，比较单句与两句批量生成，以及 Ollama 卸载、驻留和生成时的差异；报告保存在仓库外。

## 更新项目

停止正在运行的 LocalTalk，以下命令在项目根目录执行。

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

更新后核对新的 `config.json`，只把需要保留的音色、路径等设置填回，不用旧文件整份覆盖新版。默认后端已切换为 Qwen，首次启动前需完成上方模型下载；继续使用已有 Kokoro 时将 `tts_backend` 改为 `kokoro`。

准备好后启动：

```powershell
..\.venv\Scripts\python.exe .\chat_tts.py
```

后续更新前可用 `git status --short` 查看本地改动。若 Git 因配置或其他文件改动拒绝拉取，先保留并合并这些改动，不使用强制覆盖。环境、模型和音频位于仓库外，无需随代码更新重新创建或下载。

## 基本操作

| 操作 | 效果 |
| --- | --- |
| 输入问题并回车 | 流式显示回答，并分段朗读 |
| `/clear` | 清空当前对话历史 |
| `/quit` | 退出程序 |
| 修改 `speaker_id` | 选择 Kokoro 音色，重启生效 |
| 修改 `qwen_speaker` | 选择 Qwen 音色，重启生效 |
| 修改 `speech_speed` | 调整 Kokoro 语速，`1.0` 为默认，大于 1 更快 |
| 打开 `audio_output_dir` 指定的目录 | 回听最近 100 个已播放的合成片段 |
| 修改 `tts_backend` | 重启后切换 `kokoro` 或 `qwen3`，共用同一环境 |

中文女声可先对比 `3` 和 `40`，男声可试 `58` 和 `59`；这些是试听起点，不代表质量排名。完整参数、音色对应关系和排障说明见[使用说明](docs/usage.md)。

Qwen 中文声音可先对比 Serena、Vivian 和 Uncle_Fu，通过 `qwen_speaker` 选择；Kokoro 使用 `speaker_id`。两种后端共用上级目录的 `.venv`，修改配置后用同一条命令重启。详细部署与比较见 [TTS 说明](docs/tts.md)。

## 使用须知

- 当前需等本轮播放结束后再输入下一问，尚不支持语音打断；退出时会等待正在合成或播放的片段完成。
- 历史只保存在内存中，退出后清空；长对话按保守估算裁剪，不是长期记忆。
- 首段合成后即可播放，但短片段之间仍可能有停顿；分段播放不保证减少总合成时间。
- `config.json` 随仓库管理；模型、虚拟环境和生成音频在 Git 忽略范围内。音频可能包含对话内容，请勿直接作为问题附件公开。
- LLM 和 TTS 的模型权重需单独下载，分别遵循其原始许可；本项目不会校验或纠正模型回答。
- Kokoro 分段播放已有 Windows 使用反馈；当前文本接收、音频保留改动和可选 Qwen 后端只完成静态检查，仍需在目标电脑上验证。

## 相关项目

[Ollama](https://github.com/ollama/ollama) 提供本地模型服务，[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) 提供 GPU 语音合成，[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 提供 CPU 语音推理，[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh) 提供中文语音模型。

项目代码采用 [MIT 许可证](LICENSE)，第三方依赖和模型分别遵循其原始许可。

[使用说明](docs/usage.md) · [更新日志](CHANGELOG.md) · [贡献指南](CONTRIBUTING.md) · [MIT 许可证](LICENSE)
