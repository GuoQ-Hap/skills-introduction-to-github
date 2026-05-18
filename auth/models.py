from pydantic import BaseModel
from enum import IntEnum
from typing import Optional, List, Dict


class PermissionLevel(IntEnum):
    BASIC = 1       # 基础用户：工作台
    OPERATOR = 2    # 操作员：工作台 + LEANG-AGENT
    ANALYST = 3     # 分析师：工作台 + LEANG-AGENT + LEANG-DATA
    SENIOR = 4      # 高级用户：工作台 + LEANG-AGENT + LEANG-DATA + LEANG-RAG
    ADMIN = 5       # 超级管理员：全部功能 + 用户管理


PERMISSION_NAMES = {
    1: "基础用户",
    2: "操作员",
    3: "分析师",
    4: "高级用户",
    5: "超级管理员",
}

# 各预设等级对应的功能列表（用于前端自动填充）
LEVEL_PERMISSIONS: dict[int, List[str]] = {
    1: [],
    2: ["agent"],
    3: ["agent", "data"],
    4: ["agent", "data", "rag"],
    5: ["agent", "data", "rag", "system", "admin"],
}


class UserRecord(BaseModel):
    username: str
    password_hash: str
    permission_level: int
    display_name: str
    enabled: bool = True
    custom_permissions: Optional[List[str]] = None
    data_restrictions: Optional[Dict[str, List[str]]] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    display_name: str
    permission_level: int
    permission_name: str
    custom_permissions: Optional[List[str]] = None
    data_restrictions: Optional[Dict[str, List[str]]] = None


class UserInfo(BaseModel):
    username: str
    display_name: str
    permission_level: int
    permission_name: str
    enabled: bool
    custom_permissions: Optional[List[str]] = None
    data_restrictions: Optional[Dict[str, List[str]]] = None


class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str
    permission_level: int
    enabled: bool = True
    custom_permissions: Optional[List[str]] = None
    data_restrictions: Optional[Dict[str, List[str]]] = None


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    permission_level: Optional[int] = None
    enabled: Optional[bool] = None
    password: Optional[str] = None
    custom_permissions: Optional[List[str]] = None
    data_restrictions: Optional[Dict[str, List[str]]] = None
