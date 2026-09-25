from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
import numpy as np

from db.database import get_db
from db.models import BatteryInfo, BatteryLifecycleData

router = APIRouter()


@router.get("/correlation/{battery_id}")
async def get_correlation_analysis(
    battery_id: int,
    target: Optional[str] = Query("rul", description="目标变量: rul 或 pcl"),
    cycle_start: Optional[int] = Query(None, ge=0, description="起始循环次数"),
    cycle_end: Optional[int] = Query(None, ge=0, description="结束循环次数"),
    db: Session = Depends(get_db)
):
    """
    获取特征相关性分析
    计算电池生命周期数据中各特征与目标变量（RUL或PCL）的相关系数
    支持按循环次数范围筛选数据
    """
    try:
        # 验证电池是否存在
        battery = db.query(BatteryInfo).filter(BatteryInfo.battery_id == battery_id).first()
        if not battery:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"电池 {battery_id} 不存在"
            )
        
        # 获取该电池的生命周期数据，支持循环次数范围筛选
        query = db.query(BatteryLifecycleData).filter(
            BatteryLifecycleData.battery_id == battery_id
        )
        
        if cycle_start is not None:
            query = query.filter(BatteryLifecycleData.cycle_count >= cycle_start)
        if cycle_end is not None:
            query = query.filter(BatteryLifecycleData.cycle_count <= cycle_end)
        
        lifecycle_data = query.order_by(BatteryLifecycleData.cycle_count).all()
        
        if not lifecycle_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"电池 {battery_id} 没有生命周期数据"
            )
        
        # 检查是否有足够的数据点
        if len(lifecycle_data) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="数据点不足，无法计算相关性"
            )
        
        # 提取特征数据
        features = {
            'voltage': [float(d.voltage) for d in lifecycle_data],
            'current': [float(d.current) for d in lifecycle_data],
            'temperature': [float(d.temperature) for d in lifecycle_data],
            'capacity': [float(d.capacity) for d in lifecycle_data],
            'resistance': [float(d.resistance) for d in lifecycle_data],
            'soc': [float(d.soc) for d in lifecycle_data],
            'soh': [float(d.soh) for d in lifecycle_data],
            'power': [float(d.power) for d in lifecycle_data],
        }
        
        # 提取目标变量
        if target == "rul":
            target_values = [float(d.rul) for d in lifecycle_data]
        elif target == "pcl":
            target_values = [float(d.pcl) for d in lifecycle_data]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="目标变量必须是 'rul' 或 'pcl'"
            )
        
        # 计算相关系数
        correlations = {}
        feature_names = {
            'voltage': 'voltage',
            'current': 'current',
            'temperature': 'temperature',
            'capacity': 'capacity',
            'resistance': 'resistance',
            'soc': 'soc',
            'soh': 'soh',
            'power': 'power'
        }
        
        for feature_name, feature_values in features.items():
            try:
                # 使用numpy计算皮尔逊相关系数
                if len(feature_values) == len(target_values) and len(feature_values) > 1:
                    correlation = np.corrcoef(feature_values, target_values)[0, 1]
                    # 处理NaN值
                    if np.isnan(correlation):
                        correlation = 0.0
                    correlations[f'{feature_name}_{target}'] = float(correlation)
                else:
                    correlations[f'{feature_name}_{target}'] = 0.0
            except Exception:
                correlations[f'{feature_name}_{target}'] = 0.0
        
        # 为了与前端兼容，同时提供以特征名称为key的格式
        feature_correlations = {}
        for feature_name in feature_names.keys():
            key = f'{feature_name}_{target}'
            if key in correlations:
                feature_correlations[feature_name] = correlations[key]
        
        return {
            "success": True,
            "data": {
                **correlations,
                "features": feature_correlations
            },
            "target": target,
            "count": len(lifecycle_data)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"计算相关性时出错: {str(e)}"
        )


@router.get("/trend/{battery_id}")
async def get_trend_analysis(
    battery_id: int,
    interval: Optional[int] = Query(10, ge=1, le=100, description="采样间隔"),
    cycle_start: Optional[int] = Query(None, ge=0, description="起始循环次数"),
    cycle_end: Optional[int] = Query(None, ge=0, description="结束循环次数"),
    db: Session = Depends(get_db)
):
    """
    获取趋势分析数据
    返回电池生命周期数据的趋势，支持按间隔采样以减少数据量
    支持按循环次数范围筛选数据
    """
    try:
        # 验证电池是否存在
        battery = db.query(BatteryInfo).filter(BatteryInfo.battery_id == battery_id).first()
        if not battery:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"电池 {battery_id} 不存在"
            )
        
        # 获取数据，支持循环次数范围筛选
        query = db.query(BatteryLifecycleData).filter(
            BatteryLifecycleData.battery_id == battery_id
        )
        
        if cycle_start is not None:
            query = query.filter(BatteryLifecycleData.cycle_count >= cycle_start)
        if cycle_end is not None:
            query = query.filter(BatteryLifecycleData.cycle_count <= cycle_end)
        
        all_data = query.order_by(BatteryLifecycleData.cycle_count).all()
        
        if not all_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"电池 {battery_id} 没有生命周期数据"
            )
        
        # 按间隔采样
        sampled_data = [
            d for i, d in enumerate(all_data) 
            if i % interval == 0 or i == len(all_data) - 1
        ]
        
        # 如果采样后数据量仍太大，再次采样
        if len(sampled_data) > 500:
            step = len(sampled_data) // 500
            sampled_data = [sampled_data[i] for i in range(0, len(sampled_data), step)]
        
        # 提取各特征的趋势数据
        cycles = [d.cycle_count for d in sampled_data]
        voltage = [float(d.voltage) for d in sampled_data]
        current = [float(d.current) for d in sampled_data]
        temperature = [float(d.temperature) for d in sampled_data]
        capacity = [float(d.capacity) for d in sampled_data]
        resistance = [float(d.resistance) for d in sampled_data]
        soc = [float(d.soc) for d in sampled_data]
        soh = [float(d.soh) for d in sampled_data]
        power = [float(d.power) for d in sampled_data]
        rul = [float(d.rul) for d in sampled_data]
        pcl = [float(d.pcl) for d in sampled_data]
        
        return {
            "success": True,
            "data": {
                "cycles": cycles,
                "voltage": voltage,
                "current": current,
                "temperature": temperature,
                "capacity": capacity,
                "resistance": resistance,
                "soc": soc,
                "soh": soh,
                "power": power,
                "rul": rul,
                "pcl": pcl
            },
            "total_count": len(all_data),
            "sampled_count": len(sampled_data),
            "interval": interval
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取趋势数据时出错: {str(e)}"
        )
