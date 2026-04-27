from core.ollama import ollama


async def handle_chat_completion(payload: dict) -> dict:
    """
    Controllerから受け取ったpayloadをOllama API形式に変換して実行する。

    payload: {"model": "...", "messages": [...], "temperature": 0.7, "max_tokens": 2048, "stream": false}
    returns: {"message": {"role": "assistant", "content": "..."}, "usage": {...}}
    """
    messages = payload.get("messages", [])
    options: dict = {}
    if payload.get("temperature") is not None:
        options["temperature"] = payload["temperature"]
    if payload.get("max_tokens") is not None:
        options["num_predict"] = payload["max_tokens"]

    result = await ollama.chat(
        model=payload.get("model", ""),
        messages=messages,
        options=options if options else None,
    )

    message = result.get("message", {})
    # Ollamaのusage情報（eval_count等）をOpenAI形式に変換する
    prompt_eval = result.get("prompt_eval_count", 0)
    eval_count = result.get("eval_count", 0)

    return {
        "message": {"role": message.get("role", "assistant"), "content": message.get("content", "")},
        "usage": {
            "prompt_tokens": prompt_eval,
            "completion_tokens": eval_count,
            "total_tokens": prompt_eval + eval_count,
        },
    }
