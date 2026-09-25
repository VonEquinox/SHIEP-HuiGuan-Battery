from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from db.database import get_db
from db.models import User, Model, PredictionRecord, TrainingRecord, BatteryInfo
from utils.security import get_current_user
from typing import List, Dict, Any
from datetime import datetime, timedelta

router = APIRouter()


@router.get("/statistics")
async def get_dashboard_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取仪表盘统计数据
    """
    try:
        # 当前用户个性化统计
        my_training_count = db.query(func.count(TrainingRecord.id)).filter(
            TrainingRecord.user_id == current_user.id
        ).scalar() or 0
        my_prediction_count = db.query(func.count(PredictionRecord.id)).filter(
            PredictionRecord.user_id == current_user.id
        ).scalar() or 0

        # 总用户数
        total_users = db.query(func.count(User.id)).filter(User.status == True).scalar()
        
        # 当前用户的模型数
        # 和模型管理页保持一致：统计当前用户名下的所有模型；
        # 删除操作是物理删除，所以这里不用额外排除 deleted 状态
        total_models = db.query(func.count(Model.id)).filter(
            Model.user_id == current_user.id
        ).scalar() or 0
        
        # 当前用户的预测/训练任务数
        total_predictions = db.query(func.count(PredictionRecord.id)).filter(
            PredictionRecord.user_id == current_user.id
        ).scalar()
        
        total_trainings = db.query(func.count(TrainingRecord.id)).filter(
            TrainingRecord.user_id == current_user.id
        ).scalar()
        
        # 总电池数
        total_batteries = db.query(func.count(BatteryInfo.battery_id)).scalar()
        
        # 计算平均预测时长（最近30天的预测任务）
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        avg_execution_time = db.query(
            func.avg(PredictionRecord.execution_time)
        ).filter(
            PredictionRecord.user_id == current_user.id,
            PredictionRecord.prediction_time >= thirty_days_ago,
            PredictionRecord.execution_time.isnot(None)
        ).scalar()
        
        avg_execution_time_hours = (avg_execution_time / 3600) if avg_execution_time else 0
        
        # 最近活动（最近10条预测和训练记录）
        recent_predictions = db.query(PredictionRecord).filter(
            PredictionRecord.user_id == current_user.id
        ).order_by(
            PredictionRecord.prediction_time.desc()
        ).limit(5).all()
        
        recent_trainings = db.query(TrainingRecord).filter(
            TrainingRecord.user_id == current_user.id
        ).order_by(
            TrainingRecord.start_time.desc()
        ).limit(5).all()
        
        # 组装最近活动列表
        recent_activities = []
        
        # 添加预测活动
        for pred in recent_predictions:
            user = db.query(User).filter(User.id == pred.user_id).first()
            battery = db.query(BatteryInfo).filter(BatteryInfo.battery_id == pred.battery_id).first()
            recent_activities.append({
                "timestamp": pred.prediction_time.isoformat() if pred.prediction_time else None,
                "user": user.username if user else "Unknown",
                "action": "predict",
                "details": f"执行了{pred.prediction_type}预测任务（电池: {battery.battery_name if battery else pred.battery_id}）"
            })
        
        # 添加训练活动
        for train in recent_trainings:
            user = db.query(User).filter(User.id == train.user_id).first()
            model = db.query(Model).filter(Model.id == train.model_id).first()
            recent_activities.append({
                "timestamp": train.start_time.isoformat() if train.start_time else None,
                "user": user.username if user else "Unknown",
                "action": "train",
                "details": f"开始训练模型: {model.name if model else train.model_id}（状态: {train.status}）"
            })
        
        # 按时间排序
        recent_activities.sort(key=lambda x: x["timestamp"] or "", reverse=True)
        recent_activities = recent_activities[:10]  # 取最近10条
        
        # 模型使用情况统计（按算法类型）
        model_usage = db.query(
            Model.algorithm_type,
            func.count(PredictionRecord.id).label('count')
        ).join(
            PredictionRecord, Model.id == PredictionRecord.model_id
        ).filter(
            PredictionRecord.user_id == current_user.id
        ).group_by(Model.algorithm_type).all()
        
        model_usage_data = [
            {"name": usage[0] or "未知", "value": usage[1]}
            for usage in model_usage
        ]
        
        # 如果没有数据，使用默认值
        if not model_usage_data:
            model_usage_data = [
                {"name": "BiLSTM", "value": 0},
                {"name": "DeepHPM", "value": 0},
                {"name": "Baseline", "value": 0}
            ]
        
        # 准确率趋势（最近30天的预测准确率，如果有实际值）
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_predictions_with_accuracy = db.query(PredictionRecord).filter(
            PredictionRecord.user_id == current_user.id,
            PredictionRecord.prediction_time >= thirty_days_ago,
            PredictionRecord.predicted_soh.isnot(None),
            PredictionRecord.actual_soh.isnot(None)
        ).order_by(PredictionRecord.prediction_time).all()
        
        # 按时间分组计算准确率（每条记录显示一个点）
        accuracy_trend = []
                
        for pred in recent_predictions_with_accuracy:
            if pred.prediction_time and pred.actual_soh is not None and pred.predicted_soh is not None:
                actual_soh = float(pred.actual_soh)
                predicted_soh = float(pred.predicted_soh)
                
                # 数据验证：SOH应该在合理范围内（0-1之间）
                # 如果实际值太小（< 0.1），可能是数据输入错误，使用绝对误差代替相对误差
                is_data_valid = 0.0 <= actual_soh <= 1.0 and 0.0 <= predicted_soh <= 1.0
                is_actual_too_small = actual_soh < 0.1
                
                if actual_soh > 0:
                    # 计算绝对误差
                    absolute_error = abs(actual_soh - predicted_soh)
                    
                    # 如果实际值太小，使用绝对误差计算准确率（避免相对误差被放大）
                    if is_actual_too_small:
                        # 使用绝对误差：准确率 = 1 - 绝对误差（因为SOH范围是0-1）
                        raw_accuracy = 1 - absolute_error
                        relative_error = None  # 不计算相对误差，避免误导
                        accuracy = max(0.0, min(1.0, raw_accuracy))
                    else:
                        # 正常情况：使用相对误差
                        relative_error = absolute_error / actual_soh
                        raw_accuracy = 1 - relative_error
                        accuracy = max(0.0, min(1.0, raw_accuracy))
                else:
                    accuracy = 0.0
                    relative_error = None
                    absolute_error = abs(actual_soh - predicted_soh)
                
                # 返回更多信息用于调试和显示
                accuracy_trend.append({
                    "date": pred.prediction_time.strftime('%Y-%m-%d %H:%M'),
                    "accuracy": accuracy,  # 保留完整精度，不四舍五入
                    "actual_soh": actual_soh,
                    "predicted_soh": predicted_soh,
                    "absolute_error": absolute_error,
                    "relative_error": float(relative_error) if relative_error is not None else None,
                    "is_data_valid": is_data_valid,
                    "warning": "实际SOH值异常小，可能数据有误" if is_actual_too_small else None
                })
        
        return {
            "total_users": total_users or 0,
            "total_models": total_models or 0,
            "total_predictions": total_predictions or 0,
            "total_trainings": total_trainings or 0,
            "total_batteries": total_batteries or 0,
            "avg_prediction_time_hours": round(avg_execution_time_hours, 2) if avg_execution_time_hours else 0,
            "recent_activities": recent_activities,
            "model_usage": model_usage_data,
            "accuracy_trend": accuracy_trend,
            "current_user": {
                "username": current_user.username,
                "email": current_user.email,
                "my_training_count": my_training_count,
                "my_prediction_count": my_prediction_count,
            },
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计数据失败: {str(e)}"
        )
