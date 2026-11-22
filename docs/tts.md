# TTS 选型与切换

仓库配置默认选择 Qwen3 GPU 后端，接入代码仅经过静态检查，尚未在目标 GPU 上验证。Kokoro CPU 后端已有 Windows 使用反馈，可通过同一份配置切换；程序不会自动切换、卸载 Ollama 或修改上下文配置。

## 怎么选

| 方案 | 适合的尝试 | 当前接入状态 |
| --- | --- | --- |
| Kokoro v1.1 / CPU | 保持已有播放速度，给大模型留出显存 | 可切换的 CPU 后端 |
| Qwen3-TTS 0.6B CustomVoice / GPU | 比较另一套中文声音，无需参考录音 | 配置默认后端，依赖已合并到 requirements.txt |
| CosyVoice 3 / GPU | 希望进一步探索声音克隆和中文语音能力 | 未接入，暂作候选 |

Qwen 的 0.6B CustomVoice 提供预设声音，中文可先对比 Serena、Vivian、Uncle_Fu。较大的 1.7B 不作为 8GB 显卡与 Ollama 共用时的首选。当前接入不提供情绪指令或数值语速调整；0.6B 的指令能力应以官方代码和型号表为准，不能将 1.7B 的能力直接套用过来。[Qwen 官方说明](https://github.com/QwenLM/Qwen3-TTS)、[模型与音色](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice)

这是值得试听的替代方案，不是已经证实比当前音色更好的结果。对于 i5-10600KF、RTX 5060 8GB、16GB 内存的组合，剩余约 3GB 显存是否足够仍需实测：模型权重之外还有运行缓存和临时张量。接入保持相同分段与队列策略，但换模型后合成耗时可能不同，不能保证维持 Kokoro 的实时率或连贯性。

先回听单独保存的 WAV，判断毛刺是否已存在于合成音频中。若只在实时播放或片段连接时出现，换模型未必能解决。

## 统一环境

所有命令在 `localTalk` 项目根目录的 PowerShell 中执行，统一使用上级的 `..\.venv\Scripts\python.exe`。不再为 Qwen 单独创建环境，所有依赖集中在 `requirements.txt`。

先检查已有环境：

```powershell
..\.venv\Scripts\python.exe --version
```

当前依赖组合按 64 位 Python 3.12 配置，与 [Qwen 官方推荐版本](https://github.com/QwenLM/Qwen3-TTS#environment-setup)一致。这不是 PyTorch 只能使用旧 Python：[PyTorch 2.15 已支持 Python 3.15](https://pytorch.org/blog/pytorch-2-15-release-blog/)，[TorchAudio 2.11 支持 PyTorch 2.11 及后续版本](https://pypi.org/project/torchaudio/)，也不必机械地保持二者版本号相同。

截至 2026-11-21，当前完整安装路径的障碍是 [Qwen 必需依赖中的 onnxruntime](https://github.com/QwenLM/Qwen3-TTS/blob/main/pyproject.toml)：[ONNX Runtime 1.32](https://pypi.org/project/onnxruntime/1.32.0/#files) 尚未提供 Python 3.15 的 Windows 安装包，[官方支持请求](https://github.com/microsoft/onnxruntime/issues/33271)仍未解决。只升级 PyTorch 不能解决这个依赖缺口。当前 requirements.txt 仍保留原组合，不代表已适配新版；升级需核对完整依赖链并验证实际合成。

若原 `.venv` 已使用兼容版本，直接补齐依赖：

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m pip check
```

若 `.venv` 尚不存在，且已通过新版 Python Install Manager 安装 3.12，可在项目根目录执行下面的命令。显式指定新版管理器，避免被旧版 `C:\Windows\py.exe` 抢先匹配；运行项目时直接使用虚拟环境中的解释器，无需激活。

```powershell
& "$env:LOCALAPPDATA\Microsoft\WindowsApps\py.exe" -V:3.12 -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install --upgrade pip
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

若使用传统 Python 启动器，创建环境的第一条命令可替换为 `py -3.12 -m venv ..\.venv`。若已有环境是其他 Python 版本，先停止程序、退出已激活的环境，将旧环境备份到工作目录外，再在原位置创建 3.12 环境；不要直接覆盖旧环境。已有兼容环境无需重建，模型、配置及音频文件也无需重新生成。

依赖文件使用 PyTorch 官方 CUDA 12.8 源，并固定 `torch==2.10.0+cu128`、`torchaudio==2.10.0+cu128`，避免安装成 CPU 版本。需要兼容的 NVIDIA 驱动，采用 PyTorch SDPA，无需额外编译 FlashAttention。[PyTorch 官方版本列表](https://pytorch.org/get-started/previous-versions/#v2100)

### 检查 GPU 与依赖

在项目根目录执行统一环境检查，无需再复制多段临时 Python 命令：

```powershell
..\.venv\Scripts\python.exe .\check_env.py
```

脚本使用运行它的解释器，显示其路径、基础环境、版本、位数，以及是否使用仓库上级的 `.venv`；复用主程序的配置校验和 Qwen 路径解析，不依赖已安装的 TTS 包才能启动。

- 依赖：读取唯一的 `requirements.txt` 核对已安装版本，并执行 `pip check` 检查传递依赖兼容性。
- 模型：按当前后端检查本地关键文件。在线 Qwen 模型 ID 只提示尚未验证，不触发下载；文件存在不代表哈希、完整分片或模型内容已验证。
- Qwen：通过 `nvidia-smi` 显示显卡、驱动及总量 / 已用 / 剩余显存（MiB），在 `cuda:0` 上执行小规模 BF16 矩阵乘法，预期结果为 `32.0`；另行检查 Qwen 与音频依赖能否导入。
- Kokoro：检查 sherpa-onnx 与音频依赖导入，不要求 CUDA 运算通过。
- Ollama：从配置的对话地址访问对应的 `/api/tags`，检查服务是否可访问、指定模型是否已安装，不运行对话模型。

每项显示“通过 / 注意 / 失败”和必要的处理建议，一项失败后继续检查其余独立项目；配置无效时跳过依赖配置的检查。外部命令单项超时 60 秒，Ollama 连接超时 5 秒。存在失败项时退出码为 1，否则为 0；只有注意项时仍需阅读提示，不能当作完整功能验收。

脚本不安装依赖、下载模型、合成或播放音频。显存是检查时的快照，不证明 LLM 与 TTS 同时运行时显存足够；声卡输出、音质、完整模型加载仍需实际启动验证。报告包含本机路径，公开反馈前请脱敏。

## 模型目录

两个 TTS 模型均与 `localTalk` 同级，默认配置为：

```json
{
  "tts_model_dir": "../kokoro-multi-lang-v1_1",
  "qwen_model": "../Qwen3-TTS-12Hz-0.6B-CustomVoice",
  "audio_output_dir": "../output/segments"
}
```

以上是完整 `config.json` 中的路径字段，不要用这个片段覆盖整个文件。路径以脚本所在目录为基准，也可以使用其他目录的绝对路径。`*_desc` 仅作说明，不参与推理，不会发送给 Ollama。

本地路径建议以 `../`、`./` 开头或使用绝对路径。明确指定的本地目录不存在时，程序会提示先下载或修正路径。也可填写 Hugging Face 模型 ID，由官方加载接口下载到其缓存；要保持上面的目录结构，使用下方下载命令并保留默认相对路径。

已有 Kokoro 模型保持原位。若此前已将 Qwen 下载到 `localTalk/models/Qwen3-TTS-12Hz-0.6B-CustomVoice`，先退出助手，再把整个模型目录移动到 `localTalk` 的上一级，与 Kokoro 同级；确认目标位置没有同名目录后再移动，避免嵌套或覆盖已有模型。无需重新下载。

尚未下载 Qwen 时，可用统一环境中的 ModelScope 下载到上级目录：

```powershell
..\.venv\Scripts\python.exe -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice', local_dir='../Qwen3-TTS-12Hz-0.6B-CustomVoice')"
```

也可选用 Hugging Face，两个命令任选其一：

```powershell
..\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice', local_dir='../Qwen3-TTS-12Hz-0.6B-CustomVoice')"
```

只有首次使用且缺少 Kokoro 模型时，才需要下载并解压到上一级：

```powershell
curl.exe -L --fail --retry 3 -C - -o ../kokoro-multi-lang-v1_1.tar.bz2 "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_1.tar.bz2"
..\.venv\Scripts\python.exe -c "import tarfile; tarfile.open('../kokoro-multi-lang-v1_1.tar.bz2').extractall('..', filter='data')"
```

下载成功后再解压；已有模型不用执行。Ollama 的对话模型由 Ollama 管理，保持原有位置即可。

## 配置并启动

仓库的 `config.json` 默认启用 `qwen3`、0.6B CustomVoice 和 Serena 音色。`speech_speed` 保持 `1.0`，当前接入不提供 Qwen 数值语速控制。Kokoro 的 `speaker_id`、`tts_model_dir` 和 `tts_threads` 在 Qwen 后端不生效。

```powershell
..\.venv\Scripts\python.exe .\chat_tts.py
```

切换至 Kokoro 只需修改 `tts_backend` 为 `kokoro`，使用相同命令重启。无需更换环境或依赖文件。旧配置没有 `tts_backend` 时仍使用 Kokoro。

当前 Qwen 调用 `generate_custom_voice` 完成一个片段后再播放，不是模型内部逐音频帧的流式输出。Base 声音克隆和 VoiceDesign 尚未接入，不能只替换模型目录就使用。

## 比较与验证

先测试短句，再用相同故事比较音质、首段提交播放时间、片段间等待和实时率。同时用 `nvidia-smi` 观察与 Ollama 同时运行的显存占用；显存不足时可以尝试将 `context_tokens` 从 32768 降为 16384，但这不保证一定够用。

播放完成的片段写入 `audio_output_dir`，默认是仓库上一级的 `output/segments`，按目录内本程序命名的文件保留最近 100 段。旧音频不会自动搬迁；若需要沿用历史，可在停机后迁入新目录，下次保存音频时执行保留数量清理。

Qwen3 和 [CosyVoice 3](https://github.com/QwenAudio/CosyVoice) 的代码与模型分别遵循其原始许可证；本项目不分发它们的权重。
