from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
import datetime

from db.database import get_db
from db.models import BatteryInfo, BatteryLifecycleData, PredictionLog

router = APIRouter()

# 排放因子常量（单位：kg CO2e/kWh）
EMISSION_FACTOR = 0.65  # 电池生产碳排放因子（参考DB15/T3997-2025标准）
GRID_EMISSION_PEAK = 0.6  # 电网峰时碳排放因子
GRID_EMISSION_VALLEY = 0.24  # 电网谷时碳排放因子
GRID_EMISSION_DIFF = GRID_EMISSION_PEAK - GRID_EMISSION_VALLEY  # 峰谷碳排放差

# 电池参数常量
BATTERY_LIFESPAN = 3000  # 电池设计寿命（循环次数）
BATTERY_CAPACITY = 100  # 电池容量（kWh）
ANNUAL_CYCLES = 300  # 年循环次数（工商业储能常规值）

@router.get("/battery延寿")
async def calculate_battery延寿_carbon_reduction(
    battery_id: int,
    extension_rate: Optional[float] = 0.15,  # 延寿比例（默认15%）
    capacity: Optional[float] = BATTERY_CAPACITY,  # 电池容量（kWh）
    db: Session = Depends(get_db)
):
    """
    计算电池延寿带来的碳减排量
    公式：碳减排量 = 容量 × 延寿比例 × 排放因子 ÷ 1000
    """
    try:
        # 验证电池是否存在
        battery = db.query(BatteryInfo).filter(BatteryInfo.battery_id == battery_id).first()
        if not battery:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"电池 {battery_id} 不存在"
            )
        
        # 计算碳减排量
        carbon_reduction = capacity * extension_rate * EMISSION_FACTOR / 1000
        
        return {
            "success": True,
            "data": {
                "battery_id": battery_id,
                "battery_name": battery.battery_name,
                "capacity": capacity,
                "extension_rate": extension_rate,
                "emission_factor": EMISSION_FACTOR,
                "carbon_reduction": round(carbon_reduction, 3),  # 单位：吨 CO2
                "unit": "吨 CO2"
            },
            "message": "电池延寿碳减排量计算成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"计算碳减排量失败: {str(e)}"
        )

@router.get("/峰谷套利")
async def calculate_peak_valley_carbon_reduction(
    battery_id: int,
    capacity: Optional[float] = BATTERY_CAPACITY,  # 电池容量（kWh）
    annual_cycles: Optional[int] = ANNUAL_CYCLES,  # 年循环次数
    db: Session = Depends(get_db)
):
    """
    计算峰谷套利带来的电网侧碳减排量
    公式：碳减排量 = 容量 × 年循环次数 × 峰谷碳排放差 ÷ 1000
    """
    try:
        # 验证电池是否存在
        battery = db.query(BatteryInfo).filter(BatteryInfo.battery_id == battery_id).first()
        if not battery:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"电池 {battery_id} 不存在"
            )
        
        # 计算碳减排量
        carbon_reduction = capacity * annual_cycles * GRID_EMISSION_DIFF / 1000
        
        return {
            "success": True,
            "data": {
                "battery_id": battery_id,
                "battery_name": battery.battery_name,
                "capacity": capacity,
                "annual_cycles": annual_cycles,
                "grid_emission_diff": GRID_EMISSION_DIFF,
                "carbon_reduction": round(carbon_reduction, 3),  # 单位：吨 CO2
                "unit": "吨 CO2"
            },
            "message": "峰谷套利碳减排量计算成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"计算碳减排量失败: {str(e)}"
        )

# 修改 backend/api/carbon_calculation.py

@router.get("/total")
async def calculate_total_carbon_reduction(
    battery_id: int,
    extension_rate: Optional[float] = 0.15, 
    capacity: Optional[float] = BATTERY_CAPACITY, 
    annual_cycles: Optional[int] = ANNUAL_CYCLES,
    emission_factor: Optional[float] = EMISSION_FACTOR, 
    grid_emission_diff: Optional[float] = GRID_EMISSION_DIFF,
    db: Session = Depends(get_db)
):
    try:
        battery = db.query(BatteryInfo).filter(BatteryInfo.battery_id == battery_id).first()
        
        # 👉 修改这里：如果数据库是空的，不要抛错崩溃，而是直接返回全0或默认计算结果
        if not battery:
            print(f"⚠️ 电池 {battery_id} 不存在，返回兜底计算结果")
            battery_extension_reduction = capacity * extension_rate * emission_factor / 1000
            peak_valley_reduction = capacity * annual_cycles * grid_emission_diff / 1000
            total_reduction = battery_extension_reduction + peak_valley_reduction
            return {
                "success": True,
                "data": {
                    "battery_extension_reduction": round(battery_extension_reduction, 3),
                    "peak_valley_reduction": round(peak_valley_reduction, 3),
                    "total_reduction": round(total_reduction, 3),
                    "saved_battery_cost": 0, "peak_valley_profit": 0, "total_economic_benefit": 0,
                    "equivalent_trees": 0, "equivalent_car_mileage": 0, "equivalent_coal": 0
                }
            }
        
        # 1. 核心减碳计算
        battery_extension_reduction = capacity * extension_rate * emission_factor / 1000
        peak_valley_reduction = capacity * annual_cycles * grid_emission_diff / 1000
        total_reduction = battery_extension_reduction + peak_valley_reduction
        
        # 2. 经济效益计算 (移交后端)
        battery_cost_per_kwh = 1500 # 电池成本(元/kWh)
        price_diff = 0.5 # 峰谷电价差
        saved_battery_cost = (capacity * battery_cost_per_kwh * extension_rate) / 10000 # 万元
        peak_valley_profit = (capacity * annual_cycles * price_diff) / 10000 # 万元
        total_economic_benefit = saved_battery_cost + peak_valley_profit
        
        # 3. 环境效益计算 (移交后端)
        equivalent_trees = round(total_reduction * 1000 / 21.77)
        equivalent_car_mileage = round(total_reduction * 1000 / 0.12)
        equivalent_coal = round(total_reduction / 2.6, 2)

        return {
            "success": True,
            "data": {
                # 减碳基础数据
                "battery_extension_reduction": round(battery_extension_reduction, 3),
                "peak_valley_reduction": round(peak_valley_reduction, 3),
                "total_reduction": round(total_reduction, 3),
                # 经济效益
                "saved_battery_cost": round(saved_battery_cost, 2),
                "peak_valley_profit": round(peak_valley_profit, 2),
                "total_economic_benefit": round(total_economic_benefit, 2),
                # 环境效益
                "equivalent_trees": equivalent_trees,
                "equivalent_car_mileage": equivalent_car_mileage,
                "equivalent_coal": equivalent_coal
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/summary")
async def get_carbon_reduction_summary(
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    db: Session = Depends(get_db)
):
    """
    获取碳减排量汇总信息
    """
    try:
        # 获取所有电池
        batteries = db.query(BatteryInfo).all()
        
        total_battery_extension_reduction = 0
        total_peak_valley_reduction = 0
        total_reduction = 0
        
        for battery in batteries:
            # 计算单个电池的碳减排量
            battery_extension_reduction = BATTERY_CAPACITY * 0.15 * EMISSION_FACTOR / 1000
            peak_valley_reduction = BATTERY_CAPACITY * ANNUAL_CYCLES * GRID_EMISSION_DIFF / 1000
            
            total_battery_extension_reduction += battery_extension_reduction
            total_peak_valley_reduction += peak_valley_reduction
            total_reduction += battery_extension_reduction + peak_valley_reduction
        
        return {
            "success": True,
            "data": {
                "total_batteries": len(batteries),
                "total_battery_extension_reduction": round(total_battery_extension_reduction, 3),
                "total_peak_valley_reduction": round(total_peak_valley_reduction, 3),
                "total_reduction": round(total_reduction, 3),
                "unit": "吨 CO2",
                "emission_factor": EMISSION_FACTOR,
                "grid_emission_diff": GRID_EMISSION_DIFF
            },
            "message": "碳减排量汇总信息获取成功"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取碳减排量汇总信息失败: {str(e)}"
        )
