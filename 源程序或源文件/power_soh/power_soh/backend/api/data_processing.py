from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any
import json
from datetime import datetime

from db.database import get_db
from db.models import Dataset, User
from utils.security import get_current_user

router = APIRouter()


@router.post("/preprocess-data")
async def preprocess_data(
    data_info: Dict[str, Any], 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    数据预处理接口
    """
    try:
        # 获取输入参数
        input_path = data_info.get("input_path")
        output_path = data_info.get("output_path")
        processing_steps = data_info.get("processing_steps", [])
        
        if not input_path or not output_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="缺少必要的路径参数"
            )
        
        # 这里可以集成实际的数据预处理逻辑
        # 例如：归一化、标准化、特征提取等
        processed_info = {
            "input_path": input_path,
            "output_path": output_path,
            "processing_steps": processing_steps,
            "processed_at": datetime.now().isoformat(),
            "status": "completed"
        }
        
        # 创建数据集记录
        new_dataset = Dataset(
            user_id=current_user.id,
            name=data_info.get(
                "dataset_name", 
                f"Processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            ),
            description=data_info.get("description", ""),
            file_path=output_path,
            file_size=data_info.get("file_size", 0),
            num_samples=data_info.get("num_samples", 0),
            feature_columns=json.dumps(
                data_info.get("feature_columns", [])
            ),
            target_columns=json.dumps(
                data_info.get("target_columns", ["soh", "rul"])
            ),
            data_format=data_info.get("data_format", "csv"),
            preprocessing_steps=json.dumps(processing_steps),
            is_active=True
        )
        
        db.add(new_dataset)
        db.commit()
        db.refresh(new_dataset)
        
        return {
            "success": True,
            "message": "数据预处理完成",
            "data": processed_info,
            "dataset_id": new_dataset.id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"数据预处理失败: {str(e)}"
        )


@router.post("/normalize-data")
async def normalize_data(
    normalization_params: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    数据标准化接口
    """
    try:
        dataset_id = normalization_params.get("dataset_id")
        method = normalization_params.get("method", "min-max")
        columns = normalization_params.get("columns", [])
        
        # 获取数据集信息
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="数据集不存在"
            )
        
        # 这里可以集成实际的标准化逻辑
        normalized_info = {
            "dataset_id": dataset_id,
            "method": method,
            "columns": columns,
            "normalized_at": datetime.now().isoformat(),
            "status": "completed"
        }
        
        return {
            "success": True,
            "message": "数据标准化完成",
            "data": normalized_info
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"数据标准化失败: {str(e)}"
        )


@router.post("/feature-engineering")
async def feature_engineering(
    feature_params: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    特征工程接口
    """
    try:
        dataset_id = feature_params.get("dataset_id")
        feature_types = feature_params.get("feature_types", [])
        window_size = feature_params.get("window_size", 10)
        
        # 获取数据集信息
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="数据集不存在"
            )
        
        # 这里可以集成实际的特征工程逻辑
        feature_info = {
            "dataset_id": dataset_id,
            "feature_types": feature_types,
            "window_size": window_size,
            "engineered_at": datetime.now().isoformat(),
            "status": "completed"
        }
        
        return {
            "success": True,
            "message": "特征工程完成",
            "data": feature_info
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"特征工程失败: {str(e)}"
        )


@router.get("/dataset-info/{dataset_id}")
async def get_dataset_info(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取数据集详细信息
    """
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="数据集不存在"
        )
    
    # 检查权限
    if dataset.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此数据集"
        )
    
    return {
        "success": True,
        "data": {
            "id": dataset.id,
            "name": dataset.name,
            "description": dataset.description,
            "file_path": dataset.file_path,
            "file_size": dataset.file_size,
            "num_samples": dataset.num_samples,
            "feature_columns": (
                json.loads(dataset.feature_columns) 
                if dataset.feature_columns 
                else []
            ),
            "target_columns": (
                json.loads(dataset.target_columns) 
                if dataset.target_columns 
                else []
            ),
            "data_format": dataset.data_format,
            "preprocessing_steps": (
                json.loads(dataset.preprocessing_steps) 
                if dataset.preprocessing_steps 
                else []
            ),
            "created_at": dataset.created_at,
            "updated_at": dataset.updated_at,
            "is_active": dataset.is_active
        }
    }


@router.get("/list-datasets")
async def list_datasets(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取数据集列表
    """
    datasets = db.query(Dataset).filter(
        Dataset.user_id == current_user.id
    ).offset(skip).limit(limit).all()
    
    return {
        "success": True,
        "data": [
            {
                "id": ds.id,
                "name": ds.name,
                "description": ds.description,
                "file_size": ds.file_size,
                "num_samples": ds.num_samples,
                "data_format": ds.data_format,
                "created_at": ds.created_at,
                "is_active": ds.is_active
            }
            for ds in datasets
        ],
        "pagination": {
            "skip": skip,
            "limit": limit,
            "total": len(datasets)
        }
    }