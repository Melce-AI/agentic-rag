from functools import lru_cache
from pathlib import Path

from src.core.config import get_settings


@lru_cache
def load_private_key() -> str:
    path = get_settings().jwt_private_key_path
    return Path(path).read_text(encoding="utf-8")


@lru_cache
def load_public_key() -> str:
    path = get_settings().jwt_public_key_path
    return Path(path).read_text(encoding="utf-8")
