from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from db.database import get_db
from db.models import BatteryInfo, BatteryLifecycleData, DataStatistics
from utils.security import get_current_user
from db.models import User

router = APIRouter()


@router.get("")
@router.get("/")
async def get_batteries(
    dataset_type: Optional[str] = Query(None, description="数据集类型: train, validation, test"),
    status_filter: Optional[str] = Query(None, description="状态: active, retired, testing"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    获取电池列表
    """
    query = db.query(BatteryInfo)
    
    if dataset_type:
        query = query.filter(BatteryInfo.dataset_type == dataset_type)
    if status_filter:
        query = query.filter(BatteryInfo.status == status_filter)
    
    batteries = query.offset(skip).limit(limit).all()
    total = query.count()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [
            {
                "battery_id": b.battery_id,
                "battery_name": b.battery_name,
                "manufacturer": b.manufacturer,
                "model": b.model,
                "rated_capacity": float(b.rated_capacity) if b.rated_capacity else None,
                "rated_voltage": float(b.rated_voltage) if b.rated_voltage else None,
                "status": b.status.value if b.status else None,
                "dataset_type": b.dataset_type.value if b.dataset_type else None,
                "total_cycles": b.total_cycles,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in batteries
        ]
    }


@router.get("/{battery_id}")
async def get_battery(
    battery_id: int,
    db: Session = Depends(get_db)
):
    """
    获取指定电池的详细信息
    """
    battery = db.query(BatteryInfo).filter(BatteryInfo.battery_id == battery_id).first()
    if not battery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"电池 {battery_id} 不存在"
        )
    
    # 获取统计信息
    stats = db.query(DataStatistics).filter(DataStatistics.battery_id == battery_id).first()
    
    return {
        "battery_id": battery.battery_id,
        "battery_name": battery.battery_name,
        "manufacturer": battery.manufacturer,
        "model": battery.model,
        "rated_capacity": float(battery.rated_capacity) if battery.rated_capacity else None,
        "rated_voltage": float(battery.rated_voltage) if battery.rated_voltage else None,
        "manufacture_date": battery.manufacture_date.isoformat() if battery.manufacture_date else None,
        "first_use_date": battery.first_use_date.isoformat() if battery.first_use_date else None,
        "status": battery.status.value if battery.status else None,
        "dataset_type": battery.dataset_type.value if battery.dataset_type else None,
        "total_cycles": battery.total_cycles,
        "notes": battery.notes,
        "statistics": {
            "soh_mean": float(stats.soh_mean) if stats and stats.soh_mean else None,
            "soh_min": float(stats.soh_min) if stats and stats.soh_min else None,
            "soh_max": float(stats.soh_max) if stats and stats.soh_max else None,
            "rul_mean": float(stats.rul_mean) if stats and stats.rul_mean else None,
            "pcl_mean": float(stats.pcl_mean) if stats and stats.pcl_mean else None,
            "total_cycles": stats.total_cycles if stats else None,
            "data_completeness": float(stats.data_completeness) if stats and stats.data_completeness else None,
        } if stats else None,
        "created_at": battery.created_at.isoformat() if battery.created_at else None,
    }


@router.get("/{battery_id}/lifecycle-data")
@router.get("/{battery_id}/lifecycle")  # 兼容旧路径
async def get_battery_lifecycle_data(
    battery_id: int,
    cycle_start: Optional[int] = Query(None, ge=0, description="起始循环次数"),
    cycle_end: Optional[int] = Query(None, ge=0, description="结束循环次数"),
    start_cycle: Optional[int] = Query(None, ge=0, description="起始循环次数（兼容参数）"),
    end_cycle: Optional[int] = Query(None, ge=0, description="结束循环次数（兼容参数）"),
    page: Optional[int] = Query(None, ge=1, description="页码（兼容参数）"),
    page_size: Optional[int] = Query(None, ge=1, description="每页大小（兼容参数）"),
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=100000),  # 提高最大限制以支持大数据量导出
    db: Session = Depends(get_db)
):
    """
    获取电池生命周期数据
    """
    # 兼容旧参数名
    if start_cycle is not None:
        cycle_start = start_cycle
    if end_cycle is not None:
        cycle_end = end_cycle
    if page is not None and page_size is not None:
        skip = (page - 1) * page_size
        limit = page_size
    
    # 检查电池是否存在
    battery = db.query(BatteryInfo).filter(BatteryInfo.battery_id == battery_id).first()
    if not battery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"电池 {battery_id} 不存在"
        )
    
    query = db.query(BatteryLifecycleData).filter(
        BatteryLifecycleData.battery_id == battery_id
    )
    
    if cycle_start is not None:
        query = query.filter(BatteryLifecycleData.cycle_count >= cycle_start)
    if cycle_end is not None:
        query = query.filter(BatteryLifecycleData.cycle_count <= cycle_end)
    
    query = query.order_by(BatteryLifecycleData.cycle_count)
    
    total = query.count()
    data = query.offset(skip).limit(limit).all()
    
    return {
        "battery_id": battery_id,
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [
            {
                "id": d.id,
                "battery_id": d.battery_id,
                "cycle_count": d.cycle_count,
                "voltage": float(d.voltage) if d.voltage else None,
                "current": float(d.current) if d.current else None,
                "temperature": float(d.temperature) if d.temperature else None,
                "capacity": float(d.capacity) if d.capacity else None,
                "resistance": float(d.resistance) if d.resistance else None,
                "soc": float(d.soc) if d.soc else None,
                "soh": float(d.soh) if d.soh else None,
                "power": float(d.power) if d.power else None,
                "rul": d.rul,
                "pcl": float(d.pcl) if d.pcl else None,
                "test_timestamp": d.test_timestamp.isoformat() if d.test_timestamp else None,
            }
            for d in data
        ]
    }


@router.get("/{battery_id}/statistics")
async def get_battery_statistics(
    battery_id: int,
    cycle_start: Optional[int] = Query(None, ge=0, description="起始循环次数"),
    cycle_end: Optional[int] = Query(None, ge=0, description="结束循环次数"),
    db: Session = Depends(get_db)
):
    """
    获取电池统计数据
    如果提供了循环次数范围，则实时计算该范围内的统计信息
    否则返回预计算的整个电池组的统计信息
    """
    battery = db.query(BatteryInfo).filter(BatteryInfo.battery_id == battery_id).first()
    if not battery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"电池 {battery_id} 不存在"
        )
    
    # 如果提供了循环次数范围，实时计算统计信息
    if cycle_start is not None or cycle_end is not None:
        query = db.query(BatteryLifecycleData).filter(
            BatteryLifecycleData.battery_id == battery_id
        )
        
        if cycle_start is not None:
            query = query.filter(BatteryLifecycleData.cycle_count >= cycle_start)
        if cycle_end is not None:
            query = query.filter(BatteryLifecycleData.cycle_count <= cycle_end)
        
        # 实时计算统计信息
        stats = query.all()
        
        if not stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"电池 {battery_id} 在指定循环范围内没有数据"
            )
        
        def calc_stats(values):
            """计算统计指标"""
            values = [float(v) for v in values if v is not None]
            if not values:
                return {"mean": None, "min": None, "max": None, "std": None, "variance": None}
            
            mean = sum(values) / len(values)
            variance = sum((x - mean) ** 2 for x in values) / len(values)
            std = variance ** 0.5
            
            return {
                "mean": mean,
                "min": min(values),
                "max": max(values),
                "std": std,
                "variance": variance
            }
        
        voltage_values = [d.voltage for d in stats if d.voltage is not None]
        current_values = [d.current for d in stats if d.current is not None]
        temperature_values = [d.temperature for d in stats if d.temperature is not None]
        capacity_values = [d.capacity for d in stats if d.capacity is not None]
        resistance_values = [d.resistance for d in stats if d.resistance is not None]
        soc_values = [d.soc for d in stats if d.soc is not None]
        soh_values = [d.soh for d in stats if d.soh is not None]
        power_values = [d.power for d in stats if d.power is not None]
        rul_values = [d.rul for d in stats if d.rul is not None]
        pcl_values = [d.pcl for d in stats if d.pcl is not None]
        
        total_cycles = len(stats)
        
        return {
            "battery_id": battery_id,
            "voltage": calc_stats(voltage_values),
            "current": calc_stats(current_values),
            "temperature": calc_stats(temperature_values),
            "capacity": calc_stats(capacity_values),
            "resistance": calc_stats(resistance_values),
            "soc": calc_stats(soc_values),
            "soh": calc_stats(soh_values),
            "power": calc_stats(power_values),
            "rul": calc_stats(rul_values),
            "pcl": calc_stats(pcl_values),
            "total_cycles": total_cycles,
            "data_completeness": None,
            "last_updated": None,
        }
    
    # 否则返回预计算的统计信息
    stats = db.query(DataStatistics).filter(DataStatistics.battery_id == battery_id).first()
    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"电池 {battery_id} 的统计数据不存在"
        )
    
    def to_float(value):
        return float(value) if value is not None else None
    
    return {
        "battery_id": battery_id,
        "voltage": {
            "mean": to_float(stats.voltage_mean),
            "min": to_float(stats.voltage_min),
            "max": to_float(stats.voltage_max),
            "std": to_float(stats.voltage_std),
            "variance": to_float(stats.voltage_variance),
        },
        "current": {
            "mean": to_float(stats.current_mean),
            "min": to_float(stats.current_min),
            "max": to_float(stats.current_max),
            "std": to_float(stats.current_std),
            "variance": to_float(stats.current_variance),
        },
        "temperature": {
            "mean": to_float(stats.temperature_mean),
            "min": to_float(stats.temperature_min),
            "max": to_float(stats.temperature_max),
            "std": to_float(stats.temperature_std),
            "variance": to_float(stats.temperature_variance),
        },
        "capacity": {
            "mean": to_float(stats.capacity_mean),
            "min": to_float(stats.capacity_min),
            "max": to_float(stats.capacity_max),
            "std": to_float(stats.capacity_std),
            "variance": to_float(stats.capacity_variance),
        },
        "resistance": {
            "mean": to_float(stats.resistance_mean),
            "min": to_float(stats.resistance_min),
            "max": to_float(stats.resistance_max),
            "std": to_float(stats.resistance_std),
            "variance": to_float(stats.resistance_variance),
        },
        "soc": {
            "mean": to_float(stats.soc_mean),
            "min": to_float(stats.soc_min),
            "max": to_float(stats.soc_max),
            "std": to_float(stats.soc_std),
            "variance": to_float(stats.soc_variance),
        },
        "soh": {
            "mean": to_float(stats.soh_mean),
            "min": to_float(stats.soh_min),
            "max": to_float(stats.soh_max),
            "std": to_float(stats.soh_std),
            "variance": to_float(stats.soh_variance),
        },
        "power": {
            "mean": to_float(stats.power_mean),
            "min": to_float(stats.power_min),
            "max": to_float(stats.power_max),
            "std": to_float(stats.power_std),
            "variance": to_float(stats.power_variance),
        },
        "rul": {
            "mean": to_float(stats.rul_mean),
            "min": stats.rul_min,
            "max": stats.rul_max,
            "std": to_float(stats.rul_std),
        },
        "pcl": {
            "mean": to_float(stats.pcl_mean),
            "min": to_float(stats.pcl_min),
            "max": to_float(stats.pcl_max),
            "std": to_float(stats.pcl_std),
        },
        "total_cycles": stats.total_cycles,
        "data_completeness": float(stats.data_completeness) if stats.data_completeness else None,
        "last_updated": stats.last_updated.isoformat() if stats.last_updated else None,
    }
