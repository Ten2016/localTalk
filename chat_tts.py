import os
from contextlib import closing
from time import perf_counter

from localtalk import VERSION
from localtalk.config import load_config
from localtalk.ollama import prepare_messages, stream_chat
from localtalk.speech import SpeechPipeline
from localtalk.text import TextChunks
from localtalk.tts import create_tts


def run_turn(session, tts, config, messages):
    start = perf_counter()
    pipeline = SpeechPipeline(tts, config, start)
    chunker = TextChunks(config)
    answer = []
    final_result = None
    first_text_seconds = None
    print("\n助手：", end="", flush=True)
    try:
        with closing(stream_chat(session, config, messages)) as stream:
            for data in stream:
                pipeline.check()
                text = data.get("message", {}).get("content", "")
                if text:
                    if first_text_seconds is None:
                        first_text_seconds = perf_counter() - start
                    answer.append(text)
                    print(text, end="", flush=True)
                    for chunk in chunker.feed(text):
                        pipeline.put(pipeline.text_queue, chunk)
                if data.get("done"):
                    final_result = data
                    break
        if final_result is None:
            raise RuntimeError("Ollama 流意外中断，回答不完整。")
        full_answer = "".join(answer).strip()
        if not full_answer:
            raise RuntimeError("Ollama 返回了空回答。")
        for chunk in chunker.feed("", final=True):
            pipeline.put(pipeline.text_queue, chunk)
        print("\n", flush=True)
        print(f"文本接收完成：{perf_counter() - start:.2f} 秒", flush=True)
        if final_result.get("done_reason") == "length":
            print("提示：回答达到输出上限，可能未说完。")
        pipeline.finish()
        if pipeline.first_play_seconds is None:
            raise RuntimeError("回答中没有可朗读的文本。")
    except BaseException:
        pipeline.cancel()
        raise

    print(
        f"首段文本：{first_text_seconds:.2f} 秒；"
        f"首段提交播放：{pipeline.first_play_seconds:.2f} 秒；"
        f"已播放：{pipeline.played_chunks} 段"
    )
    print(
        f"累计合成：{pipeline.synthesis_seconds:.2f} 秒；"
        f"音频长度：{pipeline.audio_seconds:.2f} 秒；"
        f"实时率：{pipeline.synthesis_seconds / pipeline.audio_seconds:.2f}"
    )
    print(
        f"片段间等待：累计 {pipeline.playback_gap_seconds:.2f} 秒；"
        f"最长 {pipeline.max_playback_gap_seconds:.2f} 秒"
    )
    print(
        f"输入：{final_result.get('prompt_eval_count', '?')} tokens；"
        f"输出：{final_result.get('eval_count', '?')} tokens\n"
    )
    return full_answer


def main():
    if os.name != "nt":
        raise RuntimeError("当前播放实现面向 Windows，请在 Win10 电脑上运行。")
    import requests

    config = load_config()
    print(f"LocalTalk {VERSION} · 本地语音助手")
    print(f"正在加载语音模型（{config['tts_backend']}）……", flush=True)
    tts = create_tts(config)
    print(f"模型：{config['model']}")
    print(
        f"上下文：{config['context_tokens']}；最大输出：{config['max_output_tokens']}"
    )
    if config["startup_text"].strip():
        print(f"开场语音：{config['startup_text']}", flush=True)
        greeting = SpeechPipeline(tts, config, perf_counter(), save_audio=False)
        try:
            greeting.put(greeting.text_queue, config["startup_text"])
            greeting.finish()
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"开场语音未完成：{exc}")
        finally:
            greeting.cancel()
    print("输入问题开始对话；/clear 清空历史；/quit 退出。")
    history = []
    with requests.Session() as session:
        if config["ollama_url"].startswith(("http://127.0.0.1:", "http://localhost:")):
            session.trust_env = False
        while True:
            question = input("\n你：").strip()
            if not question:
                continue
            if question == "/quit":
                return
            if question == "/clear":
                history.clear()
                print("对话历史已清空。")
                continue
            try:
                messages = prepare_messages(config, history, question)
                answer = run_turn(session, tts, config, messages)
            except (
                requests.RequestException,
                RuntimeError,
                ValueError,
                OSError,
            ) as exc:
                print(f"\n本轮未完成：{exc}\n已停止排队音频，本轮不写入对话历史。")
                continue
            history = messages[1:] + [{"role": "assistant", "content": answer}]


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n已退出。")
