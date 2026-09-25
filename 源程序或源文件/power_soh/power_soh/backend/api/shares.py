from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from db.database import get_db
from db.models import User, Share, Model, Dataset, PredictionRecord, TrainingRecord
from utils.security import get_current_user

router = APIRouter()


class CreateShareRequest(BaseModel):
    """创建分享请求"""
    resource_type: str  # model/dataset/prediction/training
    resource_id: Optional[int] = None  # 单个资源ID（兼容旧接口）
    resource_ids: Optional[List[int]] = None  # 资源ID列表（批量分享多个模型）
    shared_with_user_id: Optional[int] = None  # None表示公开分享（单用户分享）
    usernames: Optional[List[str]] = None  # 用户名列表（批量分享）
    permission: str = "read"  # read/write
    notes: Optional[str] = None
    expires_at: Optional[datetime] = None


class ShareResponse(BaseModel):
    """分享响应"""
    id: int
    resource_type: str
    resource_id: int
    owner_id: int
    owner_username: str
    shared_with_user_id: Optional[int]
    shared_with_username: Optional[str]
    permission: str
    notes: Optional[str]
    expires_at: Optional[datetime]
    created_at: datetime
    is_active: bool


@router.post("/")
async def create_share(
    share_data: CreateShareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    创建分享（支持批量分享）
    支持两种方式：
    1. 单用户分享：shared_with_user_id
    2. 批量分享：usernames（用户名列表）
    """
    # 验证资源类型（目前只支持模型）
    if share_data.resource_type != "model":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="目前只支持分享模型资源"
        )
    
    # 验证权限
    if share_data.permission not in ["read", "write"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="权限必须是 'read' 或 'write'"
        )
    
    # 验证必须指定资源（单个或批量）
    resource_ids = []
    if share_data.resource_ids:
        resource_ids = share_data.resource_ids
    elif share_data.resource_id:
        resource_ids = [share_data.resource_id]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="必须指定要分享的模型（resource_id 或 resource_ids）"
        )
    
    # 验证必须指定用户（批量分享或单用户分享）
    if not share_data.shared_with_user_id and not share_data.usernames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="必须指定要分享的用户（shared_with_user_id 或 usernames）"
        )
    
    # 验证所有资源是否存在且属于当前用户
    invalid_resource_ids = []
    valid_resource_ids = []
    for resource_id in resource_ids:
        resource = db.query(Model).filter(
            Model.id == resource_id,
            Model.user_id == current_user.id
        ).first()
        
        if not resource:
            invalid_resource_ids.append(resource_id)
        else:
            valid_resource_ids.append(resource_id)
    
    if invalid_resource_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"以下模型不存在或无权分享: {', '.join(map(str, invalid_resource_ids))}"
        )
    
    if not valid_resource_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有有效的模型可分享"
        )
    
    # 处理批量分享（用户名列表）
    user_ids_to_share = []
    if share_data.usernames:
        # 根据用户名查找用户ID
        invalid_usernames = []
        for username in share_data.usernames:
            username = username.strip()
            if not username:
                continue
            
            user = db.query(User).filter(User.username == username).first()
            if not user:
                invalid_usernames.append(username)
            elif user.id == current_user.id:
                continue  # 跳过自己
            else:
                user_ids_to_share.append(user.id)
        
        if invalid_usernames:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"以下用户名不存在: {', '.join(invalid_usernames)}"
            )
        
        if not user_ids_to_share:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="没有有效的用户可分享"
            )
    
    # 处理单用户分享
    elif share_data.shared_with_user_id:
        if share_data.shared_with_user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能分享给自己"
            )
        user_ids_to_share = [share_data.shared_with_user_id]
    
    # 批量创建分享记录（多个模型 × 多个用户）
    created_shares = []
    failed_shares = []  # 格式: {"resource_id": int, "username": str}
    
    for resource_id in valid_resource_ids:
        for user_id in user_ids_to_share:
            # 检查是否已经分享给该用户
            existing_share = db.query(Share).filter(
                Share.resource_type == share_data.resource_type,
                Share.resource_id == resource_id,
                Share.owner_id == current_user.id,
                Share.shared_with_user_id == user_id,
                Share.is_active == True
            ).first()
            
            if existing_share:
                # 查询用户名用于错误提示
                user = db.query(User).filter(User.id == user_id).first()
                username = user.username if user else f"用户ID:{user_id}"
                failed_shares.append({
                    "resource_id": resource_id,
                    "username": username
                })
                continue
            
            # 创建分享记录
            new_share = Share(
                resource_type=share_data.resource_type,
                resource_id=resource_id,
                owner_id=current_user.id,
                shared_with_user_id=user_id,
                permission=share_data.permission,
                notes=share_data.notes,
                expires_at=share_data.expires_at,
                is_active=True
            )
            
            db.add(new_share)
            created_shares.append(new_share)
    
    # 提交所有新创建的分享
    if created_shares:
        db.commit()
        for share in created_shares:
            db.refresh(share)
    
    # 构建返回消息
    success_count = len(created_shares)
    model_count = len(valid_resource_ids)
    user_count = len(user_ids_to_share)
    
    message = f"成功分享 {model_count} 个模型给 {user_count} 个用户（共 {success_count} 条分享记录）"
    
    if failed_shares:
        # 统计失败的用户
        failed_users_set = set()
        for failed in failed_shares:
            failed_users_set.add(failed["username"])
        if failed_users_set:
            message += f"，{len(failed_users_set)} 个用户的部分模型已存在分享"
    
    # 获取创建的用户信息
    share_data_list = []
    for share in created_shares:
        shared_user = db.query(User).filter(User.id == share.shared_with_user_id).first()
        share_data_list.append({
            "id": share.id,
            "resource_type": share.resource_type,
            "resource_id": share.resource_id,
            "owner_id": share.owner_id,
            "owner_username": current_user.username,
            "shared_with_user_id": share.shared_with_user_id,
            "shared_with_username": shared_user.username if shared_user else None,
            "permission": share.permission,
            "notes": share.notes,
            "expires_at": share.expires_at.isoformat() if share.expires_at else None,
            "created_at": share.created_at.isoformat() if share.created_at else None,
            "is_active": share.is_active
        })
    
    return {
        "success": True,
        "message": message,
        "data": share_data_list,
        "count": success_count,
        "model_count": model_count,
        "user_count": user_count,
        "failed_shares": failed_shares
    }


@router.get("/")
async def get_my_shares(
    resource_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取我分享出去的资源列表
    """
    query = db.query(Share).filter(Share.owner_id == current_user.id)
    
    if resource_type:
        query = query.filter(Share.resource_type == resource_type)
    
    shares = query.filter(Share.is_active == True).order_by(Share.created_at.desc()).all()
    
    results = []
    for share in shares:
        # 获取被分享用户信息
        shared_with_username = None
        if share.shared_with_user_id:
            shared_user = db.query(User).filter(User.id == share.shared_with_user_id).first()
            shared_with_username = shared_user.username if shared_user else None
        
        # 获取资源名称
        resource_name = None
        if share.resource_type == "model":
            model = db.query(Model).filter(Model.id == share.resource_id).first()
            resource_name = model.name if model else None
        
        results.append({
            "id": share.id,
            "resource_type": share.resource_type,
            "resource_id": share.resource_id,
            "resource_name": resource_name,
            "shared_with_user_id": share.shared_with_user_id,
            "shared_with_username": shared_with_username,
            "permission": share.permission,
            "notes": share.notes,
            "expires_at": share.expires_at.isoformat() if share.expires_at else None,
            "created_at": share.created_at.isoformat() if share.created_at else None,
            "is_public": share.shared_with_user_id is None
        })
    
    return {
        "success": True,
        "data": results,
        "total": len(results)
    }


@router.get("/received")
async def get_received_shares(
    resource_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取我被分享的资源列表
    """
    query = db.query(Share).filter(Share.shared_with_user_id == current_user.id)
    
    if resource_type:
        query = query.filter(Share.resource_type == resource_type)
    
    # 检查分享是否过期
    now = datetime.utcnow()
    shares = query.filter(
        Share.is_active == True,
        or_(
            Share.expires_at.is_(None),
            Share.expires_at > now
        )
    ).order_by(Share.created_at.desc()).all()
    
    results = []
    for share in shares:
        # 获取资源所有者信息
        owner = db.query(User).filter(User.id == share.owner_id).first()
        owner_username = owner.username if owner else "Unknown"
        
        # 获取资源名称
        resource_name = None
        if share.resource_type == "model":
            model = db.query(Model).filter(Model.id == share.resource_id).first()
            resource_name = model.name if model else None
        
        results.append({
            "id": share.id,
            "resource_type": share.resource_type,
            "resource_id": share.resource_id,
            "resource_name": resource_name,
            "owner_id": share.owner_id,
            "owner_username": owner_username,
            "permission": share.permission,
            "notes": share.notes,
            "expires_at": share.expires_at.isoformat() if share.expires_at else None,
            "created_at": share.created_at.isoformat() if share.created_at else None
        })
    
    return {
        "success": True,
        "data": results,
        "total": len(results)
    }


@router.delete("/{share_id}")
async def delete_share(
    share_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    删除分享（只有分享者可以删除）
    """
    share = db.query(Share).filter(
        Share.id == share_id,
        Share.owner_id == current_user.id
    ).first()
    
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="分享不存在或无权删除"
        )
    
    # 软删除：设置 is_active = False
    share.is_active = False
    db.commit()
    
    return {
        "success": True,
        "message": "分享已取消"
    }


@router.get("/check-permission")
async def check_permission(
    resource_type: str,
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    检查当前用户对某个资源的权限
    返回: None（无权限）, 'owner'（所有者）, 'read'（只读）, 'write'（读写）
    """
    # 先检查是否是资源所有者
    is_owner = False
    if resource_type == "model":
        resource = db.query(Model).filter(Model.id == resource_id).first()
        if resource and resource.user_id == current_user.id:
            is_owner = True
    elif resource_type == "dataset":
        resource = db.query(Dataset).filter(Dataset.id == resource_id).first()
        if resource and resource.user_id == current_user.id:
            is_owner = True
    elif resource_type == "prediction":
        resource = db.query(PredictionRecord).filter(PredictionRecord.id == resource_id).first()
        if resource and resource.user_id == current_user.id:
            is_owner = True
    elif resource_type == "training":
        resource = db.query(TrainingRecord).filter(TrainingRecord.id == resource_id).first()
        if resource and resource.user_id == current_user.id:
            is_owner = True
    
    if is_owner:
        return {
            "success": True,
            "permission": "owner",
            "has_read": True,
            "has_write": True
        }
    
    # 检查是否有分享权限
    now = datetime.utcnow()
    share = db.query(Share).filter(
        Share.resource_type == resource_type,
        Share.resource_id == resource_id,
        Share.shared_with_user_id == current_user.id,
        Share.is_active == True,
        or_(
            Share.expires_at.is_(None),
            Share.expires_at > now
        )
    ).first()
    
    if not share:
        return {
            "success": True,
            "permission": None,
            "has_read": False,
            "has_write": False
        }
    
    return {
        "success": True,
        "permission": share.permission,
        "has_read": True,
        "has_write": share.permission == "write"
    }
