# Qwen TTS 性能测试

使用现有 `.venv`、模型和 `config.json`，无需安装新依赖。脚本实际加载 GPU 模型并合成语音；测试前退出 `chat_tts.py`，不要同时运行两份测试。以下命令在 `H:\tts\localTalk` 的 PowerShell 中执行。

## 测试内容

- `sequential`：四句话依次调用现有 TTS 适配器，每次返回一段。
- `batch2`：相同四句话，每次传入两句，调用 Qwen 官方批量接口；整批返回后才能获得音频。
- 每种方式先预热一轮，不计入正式结果；默认各测三轮，交替先后顺序，每轮设置随机种子。两种调用消耗随机数的方式不同，音频不保证完全相同，因此同时记录实际音频时长和 RTF。

不播放或保存 WAV，不请求 Ollama 生成，也不自动卸载模型。主程序仍按单句生成。报告写入上级 `output/benchmarks/tts-benchmark-时间戳.json`，每完成一轮保存一次；异常或中断时保留已完成轮次。`--output-dir` 可指定其他目录，相对路径以仓库根目录为基准。`--label` 仅标记场景，不改变实际运行状态。

## 1. 更新

```powershell
git pull --ff-only
```

确认 `config.json` 的 `tts_backend` 是 `qwen3`，测试期间保持音色和上下文配置一致。

## 2. 场景 A：TTS 独占显卡

Ollama 服务保持运行，但卸载其驻留模型。先关闭其他会请求 Ollama 的客户端，再执行：

```powershell
$cfg = Get-Content .\config.json -Raw -Encoding UTF8 | ConvertFrom-Json
ollama stop $cfg.model
ollama ps
```

确认 `ollama ps` 没有驻留模型；如果仍有其他模型，按其名称执行 `ollama stop 模型名`。这只释放运行资源，不删除模型文件。CLI 默认连接本机 Ollama；配置远端服务时需在对应服务端管理模型。

```powershell
..\.venv\Scripts\python.exe .\benchmark_tts.py --label solo
```

等待测试自行结束。预热和正式测试可能需要数分钟，脚本会逐次打印进度。

## 3. 场景 B：Ollama 驻留但不生成

等 A 的进程结束后，按项目上下文配置发送一次简短请求，将模型保留一小时。不要只用 `ollama run` 的默认上下文，否则显存条件可能与项目不同。

```powershell
$cfg = Get-Content .\config.json -Raw -Encoding UTF8 | ConvertFrom-Json
$body = @{
    model = $cfg.model
    messages = @(@{ role = "user"; content = "你好" })
    stream = $false
    think = $false
    keep_alive = "1h"
    options = @{ num_ctx = $cfg.context_tokens; num_predict = 1 }
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri $cfg.ollama_url -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
ollama ps
```

确认 `CONTEXT` 与配置一致，记录 `PROCESSOR` 是否为 `100% GPU`，然后执行：

```powershell
..\.venv\Scripts\python.exe .\benchmark_tts.py --label resident
```

此场景观察显存共存影响，不代表两个模型正在争抢计算资源。报告记录 TTS 加载前后、正式轮次前后的 Ollama `/api/ps` 状态，可检查 `context_length`、`size_vram` 和是否仍然驻留。快照失败会保存原因，不能将失败当作没有驻留模型。

## 4. 场景 C：Ollama 持续生成（可选）

先完成 A、B，有需要再做 C。持续生成比日常问答中的短暂计算重叠更重，是压力场景。

另开一个 PowerShell，在项目目录执行下面的循环。每次请求独立，不累计历史；用 Ctrl+C 停止。

```powershell
cd H:\tts\localTalk
$cfg = Get-Content .\config.json -Raw -Encoding UTF8 | ConvertFrom-Json
$body = @{
    model = $cfg.model
    messages = @(@{ role = "user"; content = "请详细讲一个温暖的旅行故事，至少写八百字。" })
    stream = $false
    think = $false
    keep_alive = "1h"
    options = @{ num_ctx = $cfg.context_tokens; num_predict = 1024 }
} | ConvertTo-Json -Depth 6
while ($true) {
    Write-Host "正在请求 Ollama 生成……"
    $reply = Invoke-RestMethod -Uri $cfg.ollama_url -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -ErrorAction Stop
    Write-Host "本次输出 tokens：" $reply.eval_count
}
```

确认这个窗口持续输出进度，在原窗口运行：

```powershell
..\.venv\Scripts\python.exe .\benchmark_tts.py --label busy
```

测试完成后停止循环。取消请求后可执行 `ollama stop $cfg.model` 释放模型；恢复正常使用时 LocalTalk 会按需加载。

## 5. 观察与判断

另开窗口观察整卡负载，Ctrl+C 停止：

```powershell
nvidia-smi --query-gpu=name,memory.used,memory.free,utilization.gpu --format=csv -l 1
```

Windows 任务管理器同时观察专用 / 共享 GPU 内存及 CUDA/Compute 图表，默认 3D 图表不能单独代表推理负载。共享内存明显上升是压力线索，不能仅凭它确定慢的原因。

| 指标 | 含义 |
| --- | --- |
| 合成耗时中位数 | 同一组四句话的生成总时间，不包括加载、预热、状态查询、打印和写报告 |
| RTF | 正式轮次合成总时间 / 音频总时长；小于 1 才具有跟上播放的吞吐能力，实际应留余量 |
| 首批可用中位数 | 第一笔调用耗时；单句返回一段，批量返回两段；不是完整助手首音延迟 |
| 张量显存峰值 | 当前 Python 进程的 PyTorch 张量峰值，含模型权重，不含 Ollama 和全部驱动开销 |
| 缓存分配器保留峰值 | 当前 PyTorch 分配器保留显存，含缓存，受之前预热和测试影响 |
| GPU / Ollama 快照 | 轮次外采样，不代表整卡峰值，也不能证明轮次内持续存在计算重叠 |

脚本在每次调用前后同步 CUDA，防止异步提交导致计时偏小；每轮重置峰值统计，不清空缓存。两种方式共享一份模型，缓存保留峰值不能当作各自独占需求。需要进一步比较时，在相同场景分别启动新进程：

```powershell
..\.venv\Scripts\python.exe .\benchmark_tts.py --label resident-single --mode sequential
..\.venv\Scripts\python.exe .\benchmark_tts.py --label resident-batch --mode batch2
```

判断顺序：

1. A 已很慢：单路推理需要优化，不能全部归因于 Ollama。
2. B 比 A 明显慢：检查显存压力和驻留状态变化；相关性不直接证明发生了显存换页。
3. C 才明显慢：计算竞争可能是主要因素，结合持续负载窗口确认。
4. batch2 更快且 RTF、首批等待、显存均可接受：才考虑接入“首句单独，后续两句批量”。批量 RTF 仍大于 1，则还不能持续跟上播放。

OOM 时脚本停止并保留报告，不自动缩小批次或切换设备。不能用未完成的单边结果计算加速比。结果接近时可交换场景顺序复测，或用 `--repeat 5` 增加轮数。

先提供 A、B 各自的两行终端汇总和 JSON 报告。报告包含模型路径、环境和 Ollama 状态，公开上传前检查本机路径。测试不试听，性能结果不能代替音质和片段衔接验证。

参考：[Qwen 批量接口](https://github.com/QwenLM/Qwen3-TTS#custom-voice-generation)、[PyTorch CUDA 计时](https://docs.pytorch.org/docs/2.10/notes/cuda.html#asynchronous-execution)、[显存统计](https://docs.pytorch.org/docs/2.10/generated/torch.cuda.memory.max_memory_allocated.html)、[Ollama 驻留接口](https://docs.ollama.com/api/ps)。
