import hashlib
import json
import logging
import os
import secrets
import tempfile
import time
import threading
from typing import Optional

from .models import UserRecord, UserInfo, PERMISSION_NAMES

logger = logging.getLogger(__name__)

USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")
TOKENS_FILE = os.path.join(os.path.dirname(__file__), "tokens.json")
TOKEN_TTL = 86400 * 7  # 7 天

_file_lock = threading.Lock()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _atomic_write_json(filepath: str, data: dict) -> None:
    """原子写入 JSON 文件：先写到临时文件再 rename，防止写一半崩溃导致文件损坏。"""
    dir_name = os.path.dirname(filepath)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, filepath)
        except BaseException:
            os.unlink(tmp_path)
            raise
    except OSError as e:
        logger.error("写入文件失败 %s: %s", filepath, e)


# ── token 持久化 ──

def _load_tokens() -> dict[str, dict]:
    if not os.path.exists(TOKENS_FILE):
        return {}
    try:
        with open(TOKENS_FILE, "r", encoding="utf-8") as f:
            tokens = json.load(f)
        now = time.time()
        cleaned = {k: v for k, v in tokens.items() if v.get("expires_at", 0) > now}
        if len(cleaned) < len(tokens):
            _save_tokens(cleaned)
        return cleaned
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning("tokens.json 读取失败，将重建: %s", e)
        return {}


def _save_tokens(tokens: dict[str, dict]) -> None:
    with _file_lock:
        _atomic_write_json(TOKENS_FILE, tokens)


# ── 用户数据 ──

def _load_users() -> dict[str, dict]:
    if not os.path.exists(USERS_FILE):
        _init_default_users()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning("users.json 读取失败，将重建默认用户: %s", e)
        _init_default_users()
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    if "leangadmin" not in users:
        users["leangadmin"] = _default_admin()
        _save_users(users)
    return users


def _save_users(users: dict[str, dict]) -> None:
    with _file_lock:
        _atomic_write_json(USERS_FILE, users)


def _default_admin() -> dict:
    return {
        "username": "leangadmin",
        "password_hash": _hash_password("leangadmin"),
        "permission_level": 5,
        "display_name": "超级管理员",
        "enabled": True,
    }


def _init_default_users() -> None:
    _save_users({"leangadmin": _default_admin()})


# ── 认证 ──

def authenticate(username: str, password: str) -> Optional[UserRecord]:
    users = _load_users()
    user_data = users.get(username)
    if not user_data:
        return None
    if not user_data.get("enabled", True):
        return None
    if user_data["password_hash"] != _hash_password(password):
        return None
    return UserRecord(**user_data)


def create_token(username: str) -> str:
    token = secrets.token_hex(32)
    tokens = _load_tokens()
    tokens[token] = {
        "username": username,
        "expires_at": time.time() + TOKEN_TTL,
    }
    _save_tokens(tokens)
    return token


def get_user_by_token(token: str) -> Optional[UserRecord]:
    tokens = _load_tokens()
    entry = tokens.get(token)
    if not entry:
        return None
    if time.time() > entry["expires_at"]:
        tokens.pop(token, None)
        _save_tokens(tokens)
        return None
    users = _load_users()
    user_data = users.get(entry["username"])
    if not user_data or not user_data.get("enabled", True):
        return None
    return UserRecord(**user_data)


def revoke_token(token: str) -> None:
    tokens = _load_tokens()
    if token in tokens:
        del tokens[token]
        _save_tokens(tokens)


# ── 用户管理 ──

def list_users() -> list[UserInfo]:
    users = _load_users()
    result = []
    for user_data in users.values():
        level = user_data["permission_level"]
        result.append(UserInfo(
            username=user_data["username"],
            display_name=user_data["display_name"],
            permission_level=level,
            permission_name=PERMISSION_NAMES.get(level, str(level)),
            enabled=user_data.get("enabled", True),
            custom_permissions=user_data.get("custom_permissions"),
            data_restrictions=user_data.get("data_restrictions"),
        ))
    return result


def get_user_by_username(username: str) -> Optional[UserRecord]:
    """按用户名读取用户（用于服务端侧权限校验与数据限制）。"""
    users = _load_users()
    user_data = users.get(username)
    if not user_data:
        return None
    if not user_data.get("enabled", True):
        return None
    return UserRecord(**user_data)


def create_user(
    username: str,
    password: str,
    display_name: str,
    permission_level: int,
    enabled: bool = True,
    custom_permissions: Optional[list] = None,
    data_restrictions: Optional[dict] = None,
) -> UserInfo:
    users = _load_users()
    if username in users:
        raise ValueError(f"用户名 '{username}' 已存在")
    if permission_level not in range(1, 6):
        raise ValueError("权限等级必须在 1-5 之间")
    user_data: dict = {
        "username": username,
        "password_hash": _hash_password(password),
        "permission_level": permission_level,
        "display_name": display_name,
        "enabled": enabled,
    }
    if custom_permissions is not None:
        user_data["custom_permissions"] = custom_permissions
    if data_restrictions is not None:
        user_data["data_restrictions"] = data_restrictions
    users[username] = user_data
    _save_users(users)
    return UserInfo(
        username=username,
        display_name=display_name,
        permission_level=permission_level,
        permission_name=PERMISSION_NAMES.get(permission_level, str(permission_level)),
        enabled=enabled,
        custom_permissions=custom_permissions,
        data_restrictions=data_restrictions,
    )


def update_user(
    username: str,
    display_name: Optional[str],
    permission_level: Optional[int],
    enabled: Optional[bool],
    password: Optional[str],
    custom_permissions: Optional[list] = None,
    clear_custom_permissions: bool = False,
    data_restrictions: Optional[dict] = None,
) -> UserInfo:
    users = _load_users()
    if username not in users:
        raise ValueError(f"用户 '{username}' 不存在")
    user_data = users[username]
    if display_name is not None:
        user_data["display_name"] = display_name
    if permission_level is not None:
        if permission_level not in range(1, 6):
            raise ValueError("权限等级必须在 1-5 之间")
        user_data["permission_level"] = permission_level
    if enabled is not None:
        user_data["enabled"] = enabled
    if password is not None and password.strip():
        user_data["password_hash"] = _hash_password(password)
    if clear_custom_permissions:
        user_data.pop("custom_permissions", None)
    elif custom_permissions is not None:
        user_data["custom_permissions"] = custom_permissions
    if data_restrictions is not None:
        if data_restrictions:
            user_data["data_restrictions"] = data_restrictions
        else:
            user_data.pop("data_restrictions", None)
    users[username] = user_data
    _save_users(users)
    level = user_data["permission_level"]
    return UserInfo(
        username=username,
        display_name=user_data["display_name"],
        permission_level=level,
        permission_name=PERMISSION_NAMES.get(level, str(level)),
        enabled=user_data.get("enabled", True),
        custom_permissions=user_data.get("custom_permissions"),
        data_restrictions=user_data.get("data_restrictions"),
    )


def delete_user(username: str) -> None:
    if username == "leangadmin":
        raise ValueError("不能删除超级管理员账户")
    users = _load_users()
    if username not in users:
        raise ValueError(f"用户 '{username}' 不存在")
    del users[username]
    _save_users(users)
    tokens = _load_tokens()
    to_remove = [t for t, v in tokens.items() if v["username"] == username]
    if to_remove:
        for t in to_remove:
            del tokens[t]
        _save_tokens(tokens)
