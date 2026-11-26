# 贡献指南

欢迎通过反馈问题、提出建议、改进文档或提交代码参与 LocalTalk。

## 反馈问题与建议

先查看仓库已有 Issues，避免重复提交。报告问题时，请提供：

- Windows、Python、Ollama 版本及所选 TTS 后端；Kokoro 附 sherpa-onnx 版本，Qwen 附 qwen-tts、PyTorch 和显卡驱动版本。
- 使用的模型名称、音色编号、语速及相关配置；火山后端附错误码与请求标识，不附密钥。
- 复现步骤、预期结果和实际结果，以及脱敏后的错误信息。

涉及等待时间时，请附程序打印的首段提交播放时间、累计合成时间和音频长度。不要公开个人对话、机器上的私有路径、访问凭证或未经授权的录音。

环境问题可运行 `..\.venv\Scripts\python.exe -m scripts.check_env`，提供脱敏后的检查报告。它不会加载模型或播放声音，但会检查依赖导入、执行小规模 GPU 运算并访问配置的 Ollama 服务。

功能建议请说明使用场景与希望解决的问题。较大的功能调整，建议先开 Issue 讨论。

## 本地开发

运行程序的环境准备见 [README](README.md)。项目直接运行，无需构建；仅做静态检查时不需要 Windows、Ollama 或语音模型。

安装开发工具：

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

开发和运行共用上级的 `.venv`，依赖仅维护 `requirements.txt`。仅做静态检查时可按该文件中的 Ruff 版本单独安装 Ruff，无需下载 GPU 依赖。检查与性能脚本放在 `scripts/`，从项目根目录使用 `python -m scripts.check_env` 或 `python -m scripts.benchmark_tts` 运行。

`chat_tts.py` 保留命令行交互和单轮对话协调，运行实现按职责放在 `localtalk/` 包内：

| 文件 | 职责 |
| --- | --- |
| `chat_tts.py` | 输入、历史更新、开场语、连接文本输出与语音播放、展示运行指标 |
| `localtalk/config.py` | 读取与校验唯一配置，确定仓库根目录 |
| `localtalk/asr.py` | 本地 Qwen3-ASR INT8 文件清单、CPU 模型加载与整段转写 |
| `localtalk/vad.py` | Silero 6.3 ONNX CPU 推理与跨帧状态 |
| `localtalk/microphone.py` | 麦克风采集、首字缓冲、停顿提交及语音输入协调 |
| `localtalk/ollama.py` | 系统提示词、上下文预算、请求参数、流式响应解析 |
| `localtalk/text.py` | 按当前后端三阶段长度门槛执行统一的分段算法 |
| `localtalk/speech.py` | 文本与音频队列、缓存复用、合成线程和播放线程 |
| `localtalk/audio_cache.py` | 音频键、WAV 完整性检查、原子保存与最近使用的 1000 条淘汰 |
| `localtalk/tts/__init__.py` | 按配置创建 TTS 后端 |
| `localtalk/tts/kokoro.py` | Kokoro CPU 模型加载、音色与语速、音频生成 |
| `localtalk/tts/qwen.py` | Qwen 路径解析、GPU 模型加载、音色与音频生成 |
| `localtalk/tts/volcengine.py` | Seed-TTS 3.0 HTTP JSONL 请求、完整性检查与 MP3 解码 |
| `scripts/check_env.py` | 独立环境诊断，复用配置校验、路径解析和模型文件清单 |
| `scripts/benchmark_tts.py` | Qwen 单句与批量性能对比，复用模型加载并记录测量报告 |

所有 TTS 后端提供 `generate(text)`，返回采样数据与采样率，并提供只含合成相关设置的 `cache_identity`。播放前统一查缓存，避免各后端重复维护保存与淘汰逻辑。火山另提供 `close()` 释放 HTTP 客户端。后端在创建时才导入推理依赖，环境检查不需要先加载模型。Ollama 流由调用方显式关闭，语音异常时也能释放 HTTP 响应。

语音输入的部署和验证见[本地语音输入](docs/asr.md)。`scripts.check_env --voice` 只检查模型文件、依赖和设备设置，不录音；实际核对采集完整性、停顿提交和错误恢复需在目标 Windows 电脑上进行。麦克风在转写及回答前关闭，语音输入只向现有对话链路提供文本问题。

`config.json` 是唯一运行配置，随仓库管理，各分组的 `desc` 集中说明参数用途及可选值。模型、虚拟环境和音频输出均放在仓库外；模型路径及 `tts.audio_output_dir` 由配置指定，拆分模块不改变相对路径基准。依赖统一维护在 `requirements.txt`，安装步骤见 [TTS 选型与切换](docs/tts.md)。

沿用四空格缩进和 UTF-8 编码，通过 Ruff 统一 Python 格式并检查常见错误；配置见 `.editorconfig` 和 `pyproject.toml`。保持改动范围集中，不引入无关框架或目录层级。

## 检查改动

```powershell
..\.venv\Scripts\python.exe -m ruff format .
..\.venv\Scripts\python.exe -m ruff format --check .
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m json.tool config.json
```

CI 执行相同的格式、静态规则和运行配置 JSON 检查，不安装运行依赖、不下载模型，也不验证真实语音功能。目前没有自动化功能测试。

涉及分句或队列时，需核对长回答完整、有序，不丢字、不漏句、不重复，文本显示不等待音频；同时试听首段等待和句间停顿。对话改动检查连续追问、`/clear`、错误恢复；播放改动需在 Windows 上验证声音与 WAV 文件、超过 1000 段后的保留行为。后端改动分别检查 Kokoro、Qwen 和火山，不能以某个后端的结果替代另一个。缓存改动需检查相同文本与参数复用、换音色或语速后未命中、损坏文件重建，以及开场语复用；核对 JSON 中首次取用与命中的次数、时间在重启后保留，淘汰时同步删除对应记录。火山需检查 JSONL 被拆成半行或合并多行、提前断流不写缓存；真实调用会产生费用，环境检查不调用云端合成。

## 提交 Pull Request

- 一次聚焦一个问题或功能，说明改动前后的行为，关联已有 Issue（如有）。
- 提交信息简洁具体，例如 `修复短回答等待标点后未及时朗读的问题`。
- 在 PR 中说明实际执行的检查及结果，明确尚未验证的场景。
- 用法或配置变化同步更新 README、使用说明和 `config.json` 中的参数说明。
- 用户可感知的功能变化由维护者统一整理进 CHANGELOG；版本入口为 `localtalk/__init__.py` 中的 `VERSION`。

提交内容应为原创或已获授权，遵循项目 [MIT 许可证](LICENSE)，保留第三方来源与许可声明。`config.json` 使用可共享的模型 ID 或相对路径；不要提交 API Key、模型权重、虚拟环境或对话音频。
