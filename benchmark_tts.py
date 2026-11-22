import argparse
import json
import platform
import shutil
import statistics
import subprocess
import sys
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit

from localtalk import VERSION
from localtalk.config import BASE, load_config
from localtalk.tts.qwen import QwenTTS


TEXTS = [
    "你好，今天我们来聊一聊周末的安排，你想在家休息，还是出去走走呢？",
    "如果天气不错，可以去附近的公园散步，看看树木和鲜花，让自己放松一下。",
    "回家以后做一顿喜欢的晚餐，再听听音乐，这样的一天也会过得很充实。",
    "不必把所有事情都安排得很满，留一点自由时间，也许会有意外的惊喜。",
]


def snapshot(config):
    import requests

    result = {}
    if shutil.which("nvidia-smi"):
        try:
            process = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=True,
            )
            result["gpu_snapshot"] = process.stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            result["gpu_snapshot_error"] = str(exc)
    else:
        result["gpu_snapshot_error"] = "找不到 nvidia-smi"
    try:
        url = urlsplit(config["ollama_url"])
        if not url.path.endswith("/api/chat"):
            raise ValueError("ollama_url 路径不是 /api/chat")
        endpoint = urlunsplit(url._replace(path=url.path[:-4] + "ps"))
        with requests.Session() as session:
            if url.hostname in ("localhost", "127.0.0.1", "::1"):
                session.trust_env = False
            response = session.get(endpoint, timeout=5)
            response.raise_for_status()
            result["ollama_models"] = response.json()["models"]
    except (requests.RequestException, ValueError, KeyError) as exc:
        result["ollama_snapshot_error"] = str(exc)
    return result


def measure(tts, torch, mode, repeat, seed):
    torch.manual_seed(seed)
    torch.cuda.synchronize(0)
    torch.cuda.reset_peak_memory_stats(0)
    calls = []
    batch_size = 1 if mode == "sequential" else 2
    for offset in range(0, len(TEXTS), batch_size):
        texts = TEXTS[offset : offset + batch_size]
        torch.cuda.synchronize(0)
        start = perf_counter()
        if mode == "sequential":
            samples, sample_rate = tts.generate(texts[0])
            waves = [samples]
        else:
            waves, sample_rate = tts.model.generate_custom_voice(
                text=texts, language="Chinese", speaker=tts.speaker
            )
        torch.cuda.synchronize(0)
        seconds = perf_counter() - start
        if sample_rate <= 0 or len(waves) != len(texts):
            raise RuntimeError("返回的采样率或音频段数不正确")
        durations = [len(wave) / sample_rate for wave in waves]
        if any(duration <= 0 for duration in durations):
            raise RuntimeError("返回了空音频")
        calls.append(
            {
                "text_indices": list(range(offset, offset + len(texts))),
                "seconds": seconds,
                "audio_seconds": durations,
                "sample_rate": sample_rate,
            }
        )
        print(
            f"  {mode} 第 {repeat} 轮，第 {len(calls)} 次调用："
            f"合成 {seconds:.2f}s / 音频 {sum(durations):.2f}s",
            flush=True,
        )
    total = sum(call["seconds"] for call in calls)
    audio = sum(sum(call["audio_seconds"]) for call in calls)
    return {
        "mode": mode,
        "repeat": repeat,
        "seed": seed,
        "seconds": total,
        "audio_seconds": audio,
        "rtf": total / audio,
        "first_audio_ready_seconds": calls[0]["seconds"],
        "peak_allocated_mib": torch.cuda.max_memory_allocated(0) / 1024**2,
        "peak_reserved_mib": torch.cuda.max_memory_reserved(0) / 1024**2,
        "calls": calls,
    }


def summarize(rounds):
    summary = {}
    for mode in ("sequential", "batch2"):
        rows = [row for row in rounds if row["mode"] == mode]
        if not rows:
            continue
        summary[mode] = {
            "rounds": len(rows),
            "median_seconds": statistics.median(row["seconds"] for row in rows),
            "aggregate_rtf": sum(row["seconds"] for row in rows)
            / sum(row["audio_seconds"] for row in rows),
            "median_first_audio_ready_seconds": statistics.median(
                row["first_audio_ready_seconds"] for row in rows
            ),
            "peak_allocated_mib": max(row["peak_allocated_mib"] for row in rows),
            "peak_reserved_mib": max(row["peak_reserved_mib"] for row in rows),
        }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Qwen 单句与两句批量合成性能对比")
    parser.add_argument("--label", required=True, help="场景标记，如 solo 或 resident")
    parser.add_argument(
        "--mode", choices=("both", "sequential", "batch2"), default="both"
    )
    parser.add_argument(
        "--repeat", type=int, default=3, help="每种方式的正式轮数，默认 3"
    )
    parser.add_argument(
        "--output-dir", default="../output/benchmarks", help="报告目录，相对仓库根目录"
    )
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat 至少为 1")
    config = load_config()
    if config["tts_backend"] != "qwen3":
        parser.error("本脚本比较 Qwen 批量推理，请将 tts_backend 设为 qwen3")
    directory = Path(args.output_dir).expanduser()
    if not directory.is_absolute():
        directory = BASE / directory
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output = directory / f"tts-benchmark-{stamp}.json"
    report = {
        "version": VERSION,
        "label": args.label,
        "created_at": datetime.now().astimezone().isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "model": config["qwen_model"],
        "speaker": config["qwen_speaker"],
        "ollama_model": config["model"],
        "context_tokens": config["context_tokens"],
        "texts": TEXTS,
        "requested_repeats": args.repeat,
        "mode": args.mode,
        "dtype": "bfloat16",
        "attention": "sdpa",
        "stage": "准备环境",
        "warmups": [],
        "rounds": [],
        "status": "running",
    }

    def save():
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    save()
    print(f"场景：{args.label}；报告：{output.resolve()}", flush=True)
    print("每种方式先预热一轮，再用相同的四句话计时；不播放或保存音频。", flush=True)
    modes = ["sequential", "batch2"] if args.mode == "both" else [args.mode]
    try:
        import torch

        report["dependencies"] = {
            name: version(name) for name in ("torch", "transformers", "qwen-tts")
        }
        report["before_load"] = snapshot(config)
        report["stage"] = "加载模型"
        save()
        print("正在加载 Qwen 模型……", flush=True)
        start = perf_counter()
        tts = QwenTTS(config)
        torch.cuda.synchronize(0)
        report["load_seconds"] = perf_counter() - start
        report["gpu"] = torch.cuda.get_device_name(0)
        report["after_load"] = snapshot(config)
        save()
        for mode in modes:
            report["stage"] = f"预热 {mode}"
            save()
            print(f"预热 {mode}，不计入汇总……", flush=True)
            report["warmups"].append(measure(tts, torch, mode, 0, 2026))
            save()
        for repeat in range(1, args.repeat + 1):
            # 交替测试顺序，降低固定先后顺序对对比结果的影响。
            for mode in modes if repeat % 2 else modes[::-1]:
                report["stage"] = f"正式测试 {mode} 第 {repeat} 轮"
                save()
                before = snapshot(config)
                row = measure(tts, torch, mode, repeat, 2026 + repeat)
                row["before"] = before
                row["after"] = snapshot(config)
                report["rounds"].append(row)
                save()
        report["status"] = "complete"
        report["stage"] = "完成"
    except KeyboardInterrupt:
        report["status"] = "interrupted"
        print("测试已中断，保留已完成的轮次。")
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"测试失败：{report['error']}")
    finally:
        report["summary"] = summarize(report["rounds"])
        save()
        print("\n汇总（只包含正式完成轮次）：")
        for mode, row in report["summary"].items():
            print(
                f"{mode}：{row['rounds']} 轮；合成耗时中位数 {row['median_seconds']:.2f}s；"
                f"RTF {row['aggregate_rtf']:.2f}；"
                f"首批可用中位数 {row['median_first_audio_ready_seconds']:.2f}s；"
                f"张量显存峰值 {row['peak_allocated_mib']:.0f} MiB；"
                f"缓存分配器保留峰值 {row['peak_reserved_mib']:.0f} MiB"
            )
        print(f"报告已保存：{output.resolve()}")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
