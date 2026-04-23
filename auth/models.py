from pydantic import BaseModel
from enum import IntEnum
from typing import Optional


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


class UserRecord(BaseModel):
    username: str
    password_hash: str
    permission_level: int
    display_name: str
    enabled: bool = True


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    display_name: str
    permission_level: int
    permission_name: str


class UserInfo(BaseModel):
    username: str
    display_name: str
    permission_level: int
    permission_name: str
    enabled: bool


class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str
    permission_level: int
    enabled: bool = True


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    permission_level: Optional[int] = None
    enabled: Optional[bool] = None
    password: Optional[str] = None
