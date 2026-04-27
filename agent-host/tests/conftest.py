import os

import pytest

# Settings モジュールがインポートされる前に必須環境変数を設定する。
# テスト実行時は実際の Controller に接続しないため、ダミー値で十分。
os.environ.setdefault("CONTROLLER_URL", "https://controller.test")
os.environ.setdefault("OLLAMA_URL", "http://ollama.test")


@pytest.fixture
def anyio_backend():
    return "asyncio"
