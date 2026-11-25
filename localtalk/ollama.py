import json


SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "你是一个中文语音助手。请使用自然、口语化的中文交流。"
        "日常问题简洁回答；用户要求故事、详细解释或完整内容时充分回答。"
        "回答需要直接朗读，避免Markdown表格、星号和表情符号。"
        "不知道的内容请明确说明，不编造实时信息或已执行的操作。"
    ),
}


def input_size(messages):
    # 保守估算，不声称精确 token 计数；另为模板预留固定开销。
    return 256 + sum(len(item["content"].encode("utf-8")) + 64 for item in messages)


def prepare_messages(config, history, question):
    config = config["llm"]
    user_message = {"role": "user", "content": question}
    budget = config["context_tokens"] - config["max_output_tokens"] - 512
    if input_size([SYSTEM_MESSAGE, user_message]) > budget:
        raise ValueError("本次输入过长，请拆分发送。")
    retained = history.copy()
    while (
        retained and input_size([SYSTEM_MESSAGE] + retained + [user_message]) > budget
    ):
        retained = retained[2:]
    removed = (len(history) - len(retained)) // 2
    if removed:
        print(f"本轮请求将省略最早的 {removed} 轮历史。")
    return [SYSTEM_MESSAGE] + retained + [user_message]


def stream_chat(session, config, messages):
    config = config["llm"]
    with session.post(
        config["url"],
        json={
            "model": config["model"],
            "messages": messages,
            "think": False,
            "stream": True,
            "keep_alive": "10m",
            "options": {
                "num_ctx": config["context_tokens"],
                "num_predict": config["max_output_tokens"],
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 20,
                "min_p": 0.0,
                "presence_penalty": 1.5,
                "repeat_penalty": 1.0,
            },
        },
        stream=True,
        timeout=(5, 120),
    ) as response:
        if not response.ok:
            raise RuntimeError(
                f"Ollama HTTP {response.status_code}：{response.text[:1000]}"
            )
        for line in response.iter_lines(chunk_size=1):
            data = json.loads(line) if line else {}
            if data.get("error"):
                raise RuntimeError(data["error"])
            yield data
            if data.get("done"):
                return
    raise RuntimeError("Ollama 流意外中断，回答不完整。")
