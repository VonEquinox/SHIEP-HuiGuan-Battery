from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import os

from db.database import get_db
from db.models import Model, User, Share
from utils.security import get_current_user

router = APIRouter()


def check_model_permission(db: Session, model_id: int, user_id: int, require_write: bool = False):
    """
    检查用户对模型的权限
    返回: (has_permission: bool, is_owner: bool, permission: str)
    """
    from datetime import datetime
    
    # 检查是否是所有者
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        return False, False, None
    
    if model.user_id == user_id:
        return True, True, "owner"
    
    # 检查是否有分享权限
    now = datetime.utcnow()
    share = db.query(Share).filter(
        Share.resource_type == "model",
        Share.resource_id == model_id,
        Share.shared_with_user_id == user_id,
        Share.is_active == True,
        or_(
            Share.expires_at.is_(None),
            Share.expires_at > now
        )
    ).first()
    
    if not share:
        return False, False, None
    
    # 如果需要写权限，检查分享权限是否为 write
    if require_write and share.permission != "write":
        return False, False, share.permission
    
    return True, False, share.permission


@router.get("/", response_model=List[dict])
async def get_models(
    skip: int = 0,
    limit: int = 100,
    algorithm_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取模型列表（包括自己创建的模型和被分享给我的模型）
    """
    import json
    
    # 获取被分享给我的模型ID列表
    now = datetime.utcnow()
    shared_models = db.query(Share).filter(
        Share.resource_type == "model",
        Share.shared_with_user_id == current_user.id,
        Share.is_active == True,
        or_(
            Share.expires_at.is_(None),
            Share.expires_at > now
        )
    ).all()
    shared_model_ids = [s.resource_id for s in shared_models]
    
    # 查询：自己的模型 + 被分享给我的模型
    if shared_model_ids:
        query = db.query(Model).filter(
            or_(
                Model.user_id == current_user.id,
                Model.id.in_(shared_model_ids)
            )
        )
    else:
        query = db.query(Model).filter(Model.user_id == current_user.id)
    
    # 过滤条件
    if algorithm_type:
        query = query.filter(Model.algorithm_type == algorithm_type)
    if is_active is not None:
        query = query.filter(Model.is_active == is_active)
    
    models = query.offset(skip).limit(limit).all()
    
    result = []
    for model in models:
        # 解析 metrics 字段
        metrics_dict = {}
        train_metrics = {}
        validation_metrics = {}
        test_metrics = {}
        
        if model.metrics:
            try:
                metrics_dict = json.loads(model.metrics)
                # 如果 metrics 包含 train, validation 和 test
                if isinstance(metrics_dict, dict):
                    train_metrics = metrics_dict.get('train', {})
                    validation_metrics = metrics_dict.get('validation', {})
                    test_metrics = metrics_dict.get('test', {})
            except (json.JSONDecodeError, TypeError):
                pass
        
        # 检查是否是共享模型
        is_shared = model.id in shared_model_ids
        is_owner = model.user_id == current_user.id
        
        # 如果是共享模型，获取分享信息
        share_info = None
        if is_shared:
            share = db.query(Share).filter(
                Share.resource_type == "model",
                Share.resource_id == model.id,
                Share.shared_with_user_id == current_user.id,
                Share.is_active == True
            ).first()
            if share:
                owner = db.query(User).filter(User.id == share.owner_id).first()
                share_info = {
                    "permission": share.permission,
                    "owner_username": owner.username if owner else "Unknown",
                    "shared_at": share.created_at.isoformat() if share.created_at else None
                }
        
        result.append({
            "id": model.id,
            "user_id": model.user_id,
            "name": model.name,
            "algorithm": model.algorithm_type,  # 前端使用 algorithm
            "algorithm_type": model.algorithm_type,
            "framework": model.framework,
            "version": "v1.0.0",  # 默认版本，如果需要可以从其他字段获取
            "description": model.description,
            "status": model.status,
            "accuracy": validation_metrics.get('r2', train_metrics.get('r2', 0.95)) if (train_metrics or validation_metrics) else 0.95,
            "is_active": model.is_active,
            "createdTime": model.created_at.isoformat() if model.created_at else None,
            "updatedTime": model.updated_at.isoformat() if model.updated_at else None,
            "trained_at": model.trained_at.isoformat() if model.trained_at else None,
            "model_path": model.model_path,
            "checkpoint_path": model.checkpoint_path,
            "model_size": model.model_size,
            # 添加指标字段
            "metrics": metrics_dict,
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
            "test_metrics": test_metrics,
            # 共享信息
            "is_owner": is_owner,
            "is_shared": is_shared,
            "share_info": share_info
        })
    
    return result


# 注意：更具体的路由必须放在前面，否则会被 /{model_id} 捕获

@router.get("/{model_id}/download")
async def download_model(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    下载模型文件（检查权限：所有者或有 read/write 权限的共享用户）
    """
    print(f"[DEBUG] 开始处理下载请求: model_id={model_id}, user_id={current_user.id}")
    
    # 检查权限
    has_permission, is_owner, permission = check_model_permission(db, model_id, current_user.id, require_write=False)
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权下载此模型"
        )
    
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        print(f"[DEBUG] 模型不存在: model_id={model_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型不存在"
        )
    
    print(f"[DEBUG] 找到模型: {model.name}, model_path={model.model_path}, checkpoint_path={model.checkpoint_path}")
    
    # 构建绝对路径
    # models.py -> api/ -> backend/ -> power_soh/
    project_root = Path(__file__).parent.parent.parent
    print(f"[DEBUG] project_root: {project_root}")

    candidate_paths = []

    # 优先使用 model_path
    if model.model_path:
        candidate_paths.append(("model_path", project_root / model.model_path))

    # 其次尝试 checkpoint_path（有些旧记录只保存了 checkpoint）
    if getattr(model, "checkpoint_path", None):
        candidate_paths.append(("checkpoint_path", project_root / model.checkpoint_path))

    if not candidate_paths:
        print(f"[DEBUG] 模型文件路径和 checkpoint 路径都为空")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型未配置可下载文件路径"
        )

    model_file_path = None
    source = None
    for src, path in candidate_paths:
        print(f"[DEBUG] 尝试 {src}: {path}, exists={path.exists()}")
        if path.exists():
            model_file_path = path
            source = src
            break

    if model_file_path is None:
        # 都不存在，给出更友好的提示
        print(f"[DEBUG] 模型文件和 checkpoint 均不存在")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型文件不存在，请检查训练结果或联系管理员重新生成模型"
        )
    
    print(f"[DEBUG] 准备返回文件({source}): {model_file_path}")
    
    # 返回文件
    return FileResponse(
        path=str(model_file_path),
        filename=f"{model.name}.pth",
        media_type="application/octet-stream"
    )


@router.post("/{model_id}/activate")
async def activate_model(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    激活模型（设置为当前活跃模型）
    """
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型不存在"
        )
    
    # 先将同一用户的所有同类型模型设置为非活跃
    db.query(Model).filter(
        Model.user_id == current_user.id,
        Model.algorithm_type == model.algorithm_type
    ).update({"is_active": False})
    
    # 设置当前模型为活跃
    model.is_active = True
    db.commit()
    
    return {
        "success": True,
        "message": f"模型 {model.name} 已设置为活跃模型"
    }


@router.get("/{model_id}", response_model=dict)
async def get_model(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取指定模型的详情
    """
    # 检查权限
    has_permission, is_owner, permission = check_model_permission(db, model_id, current_user.id, require_write=False)
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此模型"
        )
    
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型不存在"
        )
    
    # 解析 JSON 字段
    import json
    hyperparameters = {}
    architecture = {}
    input_shape = {}
    output_shape = {}
    metrics = {}
    train_metrics = {}
    validation_metrics = {}
    test_metrics = {}
    
    try:
        if model.hyperparameters:
            hyperparameters = json.loads(model.hyperparameters)
        if model.architecture:
            architecture = json.loads(model.architecture)
        if model.input_shape:
            input_shape = json.loads(model.input_shape)
        if model.output_shape:
            output_shape = json.loads(model.output_shape)
        if model.metrics:
            metrics = json.loads(model.metrics)
            # 如果 metrics 包含 train, validation 和 test
            if isinstance(metrics, dict):
                train_metrics = metrics.get('train', {})
                validation_metrics = metrics.get('validation', {})
                test_metrics = metrics.get('test', {})
    except (json.JSONDecodeError, TypeError):
        pass
    
    # 计算准确率：优先使用validation的r2，其次train的r2，最后默认值
    accuracy = 0.95
    if validation_metrics and isinstance(validation_metrics, dict):
        accuracy = validation_metrics.get('r2', train_metrics.get('r2', 0.95) if train_metrics else 0.95)
    elif train_metrics and isinstance(train_metrics, dict):
        accuracy = train_metrics.get('r2', 0.95)
    elif isinstance(metrics, dict):
        accuracy = metrics.get('r2', metrics.get('accuracy', 0.95))
    
    return {
        "id": model.id,
        "user_id": model.user_id,
        "name": model.name,
        "algorithm": model.algorithm_type,
        "algorithm_type": model.algorithm_type,
        "framework": model.framework,
        "version": "v1.0.0",
        "description": model.description,
        "hyperparameters": hyperparameters,
        "architecture": architecture,
        "input_shape": input_shape,
        "output_shape": output_shape,
        "metrics": metrics,
        "train_metrics": train_metrics,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "status": model.status,
        "accuracy": accuracy,
        "is_active": model.is_active,
        "createdTime": model.created_at.isoformat() if model.created_at else None,
        "updatedTime": model.updated_at.isoformat() if model.updated_at else None,
        "trained_at": model.trained_at.isoformat() if model.trained_at else None,
        "model_path": model.model_path,
        "checkpoint_path": model.checkpoint_path,
        "model_size": model.model_size,
    }


@router.post("/")
async def create_model(
    model_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    创建新模型
    """
    import json
    
    new_model = Model(
        user_id=current_user.id,
        name=model_data.get("name"),
        algorithm_type=model_data.get("algorithm") or model_data.get("algorithm_type"),
        framework=model_data.get("framework", "PyTorch"),
        description=model_data.get("description"),
        hyperparameters=json.dumps(model_data.get("hyperparameters", {})) if model_data.get("hyperparameters") else None,
        architecture=json.dumps(model_data.get("architecture", {})) if model_data.get("architecture") else None,
        input_shape=json.dumps(model_data.get("input_shape", {})) if model_data.get("input_shape") else None,
        output_shape=json.dumps(model_data.get("output_shape", {})) if model_data.get("output_shape") else None,
        metrics=json.dumps(model_data.get("metrics", {})) if model_data.get("metrics") else None,
        status=model_data.get("status", "completed"),
        model_path=model_data.get("model_path"),
        checkpoint_path=model_data.get("checkpoint_path"),
        model_size=model_data.get("model_size"),
        is_active=model_data.get("is_active", True)
    )
    
    db.add(new_model)
    db.commit()
    db.refresh(new_model)
    
    return {
        "success": True,
        "message": "模型创建成功",
        "data": {
            "id": new_model.id,
            "name": new_model.name,
            "algorithm": new_model.algorithm_type,
            "status": new_model.status
        }
    }


@router.put("/{model_id}")
async def update_model(
    model_id: int,
    model_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    更新模型信息
    """
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型不存在"
        )
    
    # 检查权限（所有者或有 write 权限的共享用户可以更新）
    has_permission, is_owner, permission = check_model_permission(db, model_id, current_user.id, require_write=True)
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权修改此模型（需要所有者权限或写权限）"
        )
    
    import json
    
    # 更新字段
    if "name" in model_data:
        model.name = model_data["name"]
    if "algorithm" in model_data or "algorithm_type" in model_data:
        model.algorithm_type = model_data.get("algorithm") or model_data.get("algorithm_type")
    if "framework" in model_data:
        model.framework = model_data["framework"]
    if "description" in model_data:
        model.description = model_data["description"]
    if "hyperparameters" in model_data:
        model.hyperparameters = json.dumps(model_data["hyperparameters"]) if model_data["hyperparameters"] else None
    if "architecture" in model_data:
        model.architecture = json.dumps(model_data["architecture"]) if model_data["architecture"] else None
    if "input_shape" in model_data:
        model.input_shape = json.dumps(model_data["input_shape"]) if model_data["input_shape"] else None
    if "output_shape" in model_data:
        model.output_shape = json.dumps(model_data["output_shape"]) if model_data["output_shape"] else None
    if "metrics" in model_data:
        model.metrics = json.dumps(model_data["metrics"]) if model_data["metrics"] else None
    if "status" in model_data:
        model.status = model_data["status"]
    if "model_path" in model_data:
        model.model_path = model_data["model_path"]
    if "checkpoint_path" in model_data:
        model.checkpoint_path = model_data["checkpoint_path"]
    if "model_size" in model_data:
        model.model_size = model_data["model_size"]
    if "is_active" in model_data:
        model.is_active = model_data["is_active"]
    
    db.commit()
    db.refresh(model)
    
    return {
        "success": True,
        "message": "模型更新成功",
        "data": {
            "id": model.id,
            "name": model.name,
            "status": model.status
        }
    }


@router.delete("/{model_id}")
async def delete_model(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    删除模型（物理删除，只有所有者可以删除）
    """
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型不存在"
        )
    
    # 检查权限（只有所有者可以删除）
    if model.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权删除此模型（只有所有者可以删除）"
        )
    
    # 先删除关联的训练记录和预测记录
    from db.models import TrainingRecord, PredictionRecord
    db.query(TrainingRecord).filter(TrainingRecord.model_id == model_id).delete()
    db.query(PredictionRecord).filter(PredictionRecord.model_id == model_id).delete()
    
    # 删除相关的分享记录
    db.query(Share).filter(
        Share.resource_type == "model",
        Share.resource_id == model_id
    ).delete()
    
    # 物理删除模型
    db.delete(model)
    db.commit()
    
    return {
        "success": True,
        "message": "模型删除成功"
    }
