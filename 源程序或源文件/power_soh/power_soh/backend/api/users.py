from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from fastapi.security import HTTPBearer

from db.database import get_db
from db.models import User
from utils.security import verify_token
from schemas.user import UserResponse, UserUpdate

security = HTTPBearer()


async def get_current_user(token: str = Depends(security)):
    """
    获取当前用户的依赖函数
    """
    from db.database import SessionLocal
    from db.models import User
    
    payload = verify_token(token.credentials)
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.status:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or disabled",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
    finally:
        db.close()


router = APIRouter()


@router.get("/", response_model=List[UserResponse])
async def get_users(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db)
):
    """
    获取用户列表
    """
    users = db.query(User).offset(skip).limit(limit).all()
    return users


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """
    获取指定用户信息
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    return user


@router.put("/{user_id}")
async def update_user(
    user_id: int, 
    user_update: UserUpdate, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    更新用户信息
    """
    # 只能更新自己的信息，或需要管理员权限
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 更新用户信息
    if user_update.email:
        user.email = user_update.email
    if user_update.status is not None:
        user.status = user_update.status
    if user_update.role and current_user.role == "admin":
        user.role = user_update.role
    
    db.commit()
    db.refresh(user)
    
    return {"success": True, "message": "用户信息更新成功", "data": user}


@router.delete("/{user_id}")
async def delete_user(
    user_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    删除用户
    """
    # 只能删除自己的账户，或需要管理员权限
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 不实际删除，而是将状态设为禁用
    user.status = False
    db.commit()
    
    return {"success": True, "message": "用户删除成功"}


@router.put("/{user_id}/role")
async def update_user_role(
    user_id: int,
    role_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    更新用户角色
    """
    # 需要管理员权限
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    new_role = role_data.get("role")
    if new_role not in ["user", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="角色无效"
        )
    
    user.role = new_role
    db.commit()
    db.refresh(user)
    
    return {"success": True, "message": "角色更新成功", "data": user}


@router.put("/{user_id}")
async def update_user(
    user_id: int, 
    user_update: UserUpdate, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    更新用户信息
    """
    # 只能更新自己的信息，或需要管理员权限
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # === 原有基础信息更新 ===
    if user_update.email is not None:
        user.email = user_update.email
    if user_update.status is not None:
        user.status = user_update.status
    if user_update.role is not None and current_user.role == "admin":
        user.role = user_update.role
        
    # === 新增：运维人员特征字段更新 ===
    if user_update.skills is not None:
        user.skills = user_update.skills
    if user_update.current_lat is not None:
        user.current_lat = user_update.current_lat
    if user_update.current_lng is not None:
        user.current_lng = user_update.current_lng
    if user_update.carbon_index is not None:
        user.carbon_index = user_update.carbon_index
    if user_update.work_status is not None:
        user.work_status = user_update.work_status
    
    db.commit()
    db.refresh(user)
    
    return {"success": True, "message": "用户信息更新成功", "data": user}


@router.post("/batch-delete")
async def batch_delete_users(
    user_ids: List[int],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    批量删除用户
    """
    # 需要管理员权限
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    if not users:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到要删除的用户"
        )
    
    # 将用户状态设为禁用
    for user in users:
        user.status = False
    
    db.commit()
    
    return {"success": True, "message": f"成功删除{len(users)}个用户"}