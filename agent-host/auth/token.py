import json
import os
from datetime import datetime, timezone

from jose import jwt as jose_jwt

from config.settings import settings

_CONFIG_FILENAME = "agent.json"


def load_config() -> dict | None:
    """ファイルから保存済みエージェント設定を読み込む。存在しなければNoneを返す。"""
    path = os.path.join(settings.config_dir, _CONFIG_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_config(data: dict) -> None:
    """エージェント設定をファイルへアトミックに保存する。パーミッションは0o600。"""
    path = os.path.join(settings.config_dir, _CONFIG_FILENAME)
    os.makedirs(settings.config_dir, exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)  # アトミック書き込み


def is_token_expiring_soon(token: str, threshold_minutes: int = 30) -> bool:
    """
    JWTのexpフィールドを検証なしで読み取り、有効期限が threshold_minutes 以内ならTrueを返す。
    署名キーが手元にないため get_unverified_claims を使用する。
    解析不能な場合はリフレッシュを試みるためにTrueを返す。
    """
    try:
        claims = jose_jwt.get_unverified_claims(token)
        exp = claims.get("exp")
        if exp is None:
            return False
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
        remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
        return remaining < threshold_minutes * 60
    except Exception:
        return True
