# 贡献指南

欢迎通过反馈问题、提出建议、改进文档或提交代码参与 LocalTalk。

## 反馈问题与建议

先查看仓库已有 Issues，避免重复提交。报告问题时，请提供：

- Windows、Python、Ollama 和 sherpa-onnx 版本。
- 使用的模型名称、音色编号、语速及相关配置。
- 复现步骤、预期结果和实际结果，以及脱敏后的错误信息。

涉及等待时间时，请附程序打印的首段提交播放时间、累计合成时间和音频长度。不要公开个人对话、机器上的私有路径、访问凭证或未经授权的录音。

功能建议请说明使用场景与希望解决的问题。较大的功能调整，建议先开 Issue 讨论。

## 本地开发

运行程序的环境准备见 [README](README.md)。项目直接运行，无需构建；仅做静态检查时不需要 Windows、Ollama 或语音模型。

安装开发工具：

```powershell
python -m pip install -r requirements-dev.txt
```

如果同时运行程序，请使用已有虚拟环境中的 Python，并另外安装 `requirements.txt`。

`chat_tts.py` 是程序入口，包含分句、Ollama 请求、合成与播放流程；`config.example.json` 是公开配置示例，个人配置保存在不提交的 `config.json`。模型放在 `models/` 或其他配置目录，生成音频放在 `output/`。

沿用四空格缩进和 UTF-8 编码，通过 Ruff 统一 Python 格式并检查常见错误；配置见 `.editorconfig` 和 `pyproject.toml`。保持改动范围集中，不为单文件程序引入无关框架或目录层级。

## 检查改动

```powershell
python -m ruff format .
python -m ruff format --check .
python -m ruff check .
python -m json.tool config.example.json
```

CI 执行相同的格式、静态规则和示例 JSON 检查，不安装运行依赖、不下载模型，也不验证真实语音功能。目前没有自动化功能测试。

涉及分句或队列时，需核对长回答完整、有序，不丢字、不漏句、不重复；同时试听首段等待和句间停顿。对话改动检查连续追问、`/clear`、错误恢复；播放改动需在 Windows 上验证实际声音与 WAV 文件。

## 提交 Pull Request

- 一次聚焦一个问题或功能，说明改动前后的行为，关联已有 Issue（如有）。
- 提交信息简洁具体，例如 `修复短回答等待标点后未及时朗读的问题`。
- 在 PR 中说明实际执行的检查及结果，明确尚未验证的场景。
- 用法或配置变化同步更新 README、使用说明和配置示例。
- 用户可感知的功能变化由维护者统一整理进 CHANGELOG；版本入口为 `chat_tts.py` 中的 `VERSION`。

提交内容应为原创或已获授权，遵循项目 [MIT 许可证](LICENSE)，保留第三方来源与许可声明。不要提交模型权重、虚拟环境、本机配置或对话音频。
