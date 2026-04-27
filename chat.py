#!/usr/bin/env python3
"""
ollama-control-plane チャットクライアント
使い方:
    python chat.py --url https://ocp.pontium.org --key sk-proj-xxx
    python chat.py  # 環境変数 OCP_URL / OCP_API_KEY を使用
"""

import argparse
import io
import os
import sys

# Windows ターミナルの UTF-8 強制
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

try:
    import httpx
except ImportError:
    sys.exit("httpx が必要です: pip install httpx")


DEFAULT_URL = "https://ocp.pontium.org"
DEFAULT_MODEL = "qwen2.5-coder:14b"


def chat(base_url: str, api_key: str, model: str) -> None:
    history: list[dict] = []

    print(f"接続先: {base_url}  モデル: {model}")
    print("終了するには 'exit' または Ctrl+C を入力してください\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n終了します")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q"}:
            print("終了します")
            break

        history.append({"role": "user", "content": user_input})

        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    f"{base_url}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model, "messages": history},
                )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"[エラー] HTTP {e.response.status_code}: {e.response.text}")
            history.pop()
            continue
        except httpx.RequestError as e:
            print(f"[エラー] 接続失敗: {e}")
            history.pop()
            continue

        data = resp.json()
        assistant_msg = data["choices"][0]["message"]["content"]
        history.append({"role": "assistant", "content": assistant_msg})

        usage = data.get("usage", {})
        tokens = f"  [{usage.get('total_tokens', '?')} tokens]" if usage else ""
        print(f"\nAssistant: {assistant_msg}{tokens}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="ollama-control-plane チャットクライアント")
    parser.add_argument("--url", default=os.environ.get("OCP_URL", DEFAULT_URL), help="Controller URL")
    parser.add_argument("--key", default=os.environ.get("OCP_API_KEY", ""), help="API キー")
    parser.add_argument("--model", default=os.environ.get("OCP_MODEL", DEFAULT_MODEL), help="モデル名")
    args = parser.parse_args()

    if not args.key:
        sys.exit("API キーが必要です: --key オプションまたは OCP_API_KEY 環境変数で指定してください")

    chat(args.url, args.key, args.model)


if __name__ == "__main__":
    main()
