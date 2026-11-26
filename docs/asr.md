# 本地语音输入

使用 Qwen3-ASR 0.6B INT8 转写文字，Silero VAD 6.3 判断录音边界，均固定在 CPU 上运行。语音停止后识别整段问题，继续复用现有 Ollama、对话历史、分句、TTS 和音频缓存；不是边说边出字的流式 ASR。

## 目录与依赖

沿用仓库上级的 `.venv`，模型与 `localTalk/` 同级，相对路径以仓库根目录为基准：

```text
H:/tts/
├── .venv/
├── Qwen3-TTS-12Hz-0.6B-CustomVoice/
├── sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25/
│   ├── conv_frontend.onnx
│   ├── encoder.int8.onnx
│   ├── decoder.int8.onnx
│   └── tokenizer/
├── silero-vad-v6.3/
│   └── silero_vad.onnx
├── tts-cache/
└── localTalk/
```

不移动现有 TTS 模型，不在源码目录内放权重。Ollama 的模型仍由 Ollama 管理。麦克风原始录音只在本轮内存中使用，不写入 TTS 缓存或上传给 ASR 服务；转写文字会提交给配置的 Ollama 地址。

在 `localTalk` 根目录的 PowerShell 中补齐依赖：

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

新增的直接依赖为 NumPy、CPU ONNX Runtime 和 sounddevice；VAD 直接加载官方 6.3 ONNX 文件，无需安装 Silero Python 包，也不使用 `torch.hub` 在线拉取模型。

## 首次准备模型

仅在对应模型尚未准备时执行以下命令。模型存在时复用本地文件；程序启动及 `/voice` 均不会自动下载。

下载并解压 [sherpa-onnx 提供的 Qwen3-ASR INT8 模型](https://k2-fsa.github.io/sherpa/onnx/qwen3-asr/pretrained.html)：

```powershell
Invoke-WebRequest -Uri "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25.tar.bz2" -OutFile "..\sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25.tar.bz2"
..\.venv\Scripts\python.exe -c "import tarfile; archive = '../sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25.tar.bz2'; handle = tarfile.open(archive); handle.extractall('..', filter='data'); handle.close()"
```

保留完整的 `tokenizer/`，不要用原始 Qwen safetensors 代替 ONNX 文件。主要权重约 1GB，运行内存与识别耗时仍需在目标电脑上确认。

下载固定 [Silero v6.3](https://github.com/snakers4/silero-vad/releases/tag/v6.3) 的 ONNX 文件：

```powershell
New-Item -ItemType Directory -Force "..\silero-vad-v6.3" | Out-Null
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/snakers4/silero-vad/v6.3/src/silero_vad/data/silero_vad.onnx" -OutFile "..\silero-vad-v6.3\silero_vad.onnx"
```

网络无法访问时可手动下载后按上述结构放置。不要替换为其他版本同名文件；当前状态、上下文与输入格式按 6.3 实现，文件存在不代表版本及完整性已校验。

## 检查和使用

```powershell
..\.venv\Scripts\python.exe -m scripts.check_env --voice
..\.venv\Scripts\python.exe .\chat_tts.py
```

检查脚本核对本地文件、依赖版本、Qwen3-ASR API、ONNX CPU 和麦克风输入设置，不加载识别模型、不录音。检查通过不等于实际识别通过。

- 默认键盘输入；输入 `/voice`，首次加载 ASR 与 VAD 后连续语音对话。
- 说完并持续静音约 800ms 后，关闭麦克风并识别、显示本轮问题，再生成和朗读回答。
- 助手回答完成后重新打开麦克风，不接收回答期间说的话，尚不支持语音打断或回声消除。
- 监听或识别期间按 `Ctrl+C` 取消本次输入并返回键盘，再用 `/clear` 或 `/quit`；回答期间 `Ctrl+C` 沿用原退出行为，等待当前合成或播放结束。
- ASR、VAD 加载一次后保持驻留，切回键盘不卸载；退出进程后释放。
- 空识别、设备错误、采集溢出和录音超限时明确提示，不提交不完整问题，并返回键盘。

## 参数

配置集中在 `input`、`asr`、`vad`，每个分组的 `desc` 说明用途。

| 参数 | 默认值 | 用途 |
| --- | --- | --- |
| `input.mode` | `keyboard` | 改为 `voice` 可启动后直接监听 |
| `input.microphone_device` | `null` | 系统默认麦克风，或指定输入设备编号 |
| `asr.qwen3.model_dir` | `../sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25` | 本地 ONNX 模型目录 |
| `asr.qwen3.threads` | `2` | CPU 识别线程数 |
| `asr.qwen3.language` | `Chinese` | 官方语言名，空字符串自动识别 |
| `vad.silero.model_path` | `../silero-vad-v6.3/silero_vad.onnx` | 本地 6.3 模型 |
| `vad.silero.threshold` | `0.5` | 语音判定门槛，必须在 0～1 之间 |
| `vad.min_speech_ms` | `160` | 最少累计语音时长，过滤过短触发 |
| `vad.end_silence_ms` | `800` | 提交前连续静音等待 |
| `vad.pre_roll_ms` | `320` | 开始前音频缓冲，保护首字 |
| `vad.max_utterance_seconds` | `30` | 单次录音上限，可设 5～30 秒；超限取消整轮 |

采集固定为 16kHz、单声道、float32，按 512 采样点处理；时间门槛向上取整到帧。录音段内的发音、停顿与结尾等待音频连续保留，不按 VAD 逐帧删除低概率音频。VAD 无法理解“思考中”，停顿太久可能被当作说完；可增大 `end_silence_ms`，或返回键盘输入。转写仍可能错字、漏字，不能保证语音内容逐字无误。

查看设备编号：

```powershell
..\.venv\Scripts\python.exe -m sounddevice
```

默认设备不可用时先检查 Windows 麦克风权限和输入设备，再修改 `input.microphone_device`。当前不自动回退到其他设备或采样率，避免录到错误来源。

目前只完成代码和静态检查。请在目标 Windows 电脑验证真实麦克风、首尾发音、思考停顿、中文和中英混说、退出与错误恢复，并观察 ASR 与现有 LLM/TTS 共存时的内存及延迟。
