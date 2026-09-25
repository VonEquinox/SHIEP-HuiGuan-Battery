from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import datetime

from db.database import get_db
# 引入你在 models.py 里已经写好的 WorkOrder 模型
from db.models import WorkOrder 

router = APIRouter()

# 前端发过来的 JSON 数据结构
class WorkOrderCreate(BaseModel):
    target_module: str
    alert_level: int
    dispatch_strategy: str
    notes: Optional[str] = None
    location: Optional[str] = None
    source: Optional[str] = "智能大屏"

@router.post("/create")
async def create_work_order(
    request: WorkOrderCreate,
    db: Session = Depends(get_db)
):
    """
    接收前端大屏发来的换模工单，存入数据库
    """
    try:
        # 因为 models.py 里的 WorkOrder 没有单独的 strategy 等字段
        # 我们把大屏传来的策略、位置等详细信息，优雅地拼接到 notes 备注里
        combined_notes = (
            f"【故障位置】: {request.location or '未知'}\n"
            f"【处置策略】: {request.dispatch_strategy}\n"
            f"【AI诊断详情】: {request.notes}"
        )

        # 使用 SQLAlchemy ORM 标准方式写入（它会自动匹配 work_orders 表）
        new_order = WorkOrder(
            cell_id=request.target_module,    # models.py 里叫 cell_id
            alert_level=request.alert_level,
            status="Pending",                 # 状态设为待处理
            notes=combined_notes,
            created_at=datetime.datetime.now()
        )
        
        db.add(new_order)
        db.commit()
        db.refresh(new_order) # 获取数据库自动生成的自增 id
        
        # 组装一个美观的流水号返回给前端
        order_no = f"WO-{datetime.datetime.now().strftime('%Y%m%d')}-{new_order.id:04d}"
        
        return {
            "success": True, 
            "message": "工单已成功推入后端调度数据库",
            "order_no": order_no
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"工单写入数据库失败: {str(e)}"
        )