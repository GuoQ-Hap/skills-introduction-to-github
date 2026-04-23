from fastapi import APIRouter, HTTPException, Header, Depends
from typing import Optional

from .models import (
    LoginRequest, LoginResponse, UserInfo,
    CreateUserRequest, UpdateUserRequest, PERMISSION_NAMES
)
from . import service

router = APIRouter(prefix="/auth", tags=["auth"])


def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录或 Token 无效")
    token = authorization[7:]
    user = service.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token 已过期或无效，请重新登录")
    return user


def require_admin(current_user=Depends(get_current_user)):
    if current_user.permission_level < 5:
        raise HTTPException(status_code=403, detail="需要超级管理员权限")
    return current_user


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    user = service.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误，或账户已被禁用")
    token = service.create_token(user.username)
    return LoginResponse(
        token=token,
        username=user.username,
        display_name=user.display_name,
        permission_level=user.permission_level,
        permission_name=PERMISSION_NAMES.get(user.permission_level, str(user.permission_level)),
    )


@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        service.revoke_token(authorization[7:])
    return {"message": "已退出登录"}


@router.get("/me", response_model=UserInfo)
def get_me(current_user=Depends(get_current_user)):
    return UserInfo(
        username=current_user.username,
        display_name=current_user.display_name,
        permission_level=current_user.permission_level,
        permission_name=PERMISSION_NAMES.get(current_user.permission_level, str(current_user.permission_level)),
        enabled=current_user.enabled,
    )


@router.get("/users", response_model=list[UserInfo])
def get_users(current_user=Depends(require_admin)):
    return service.list_users()


@router.post("/users", response_model=UserInfo)
def create_user(req: CreateUserRequest, current_user=Depends(require_admin)):
    try:
        return service.create_user(
            username=req.username,
            password=req.password,
            display_name=req.display_name,
            permission_level=req.permission_level,
            enabled=req.enabled,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/users/{username}", response_model=UserInfo)
def update_user(username: str, req: UpdateUserRequest, current_user=Depends(require_admin)):
    try:
        return service.update_user(
            username=username,
            display_name=req.display_name,
            permission_level=req.permission_level,
            enabled=req.enabled,
            password=req.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/users/{username}")
def delete_user(username: str, current_user=Depends(require_admin)):
    try:
        service.delete_user(username)
        return {"message": f"用户 '{username}' 已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reset-admin", summary="重置超级管理员密码（需提供 secret）")
def reset_admin(secret: str = "", new_password: str = "leangadmin"):
    import os as _os
    expected = _os.environ.get("ADMIN_RESET_SECRET", "leang@reset2024")
    if secret != expected:
        raise HTTPException(status_code=403, detail="secret 错误")
    users = service._load_users()
    if "leangadmin" not in users:
        users["leangadmin"] = service._default_admin()
    else:
        users["leangadmin"]["password_hash"] = service._hash_password(new_password)
        users["leangadmin"]["enabled"] = True
    service._save_users(users)
    return {"message": "leangadmin 密码已重置"}


def init_auth_router(app):
    service._load_users()
    app.include_router(router)
