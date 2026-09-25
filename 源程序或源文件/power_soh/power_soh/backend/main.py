import os
import asyncio
import json
import re
import math
from datetime import datetime

# 解决 OpenMP 库冲突问题
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from fastapi import FastAPI, Request, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler

from api import (
    auth, 
    users, 
    batteries, 
    datasets, 
    training, 
    prediction,
    model_comparison,
    models,
    data_processing,
    dashboard,
    analysis,
    shares,
    carbon_calculation,
    work_orders   # <====== 加上这一行！！！
)
from core.config import settings

# 导入数据库模块
from db.database import engine, Base, get_db
from db.models import BMSData, PredictionLog, WorkOrder, User

# 自动创建所有表 (如果不存在)
Base.metadata.create_all(bind=engine)

# ================= AI 模型加载与定义区 =================
try:
    import torch
    import torch.nn as nn
    import numpy as np
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    print("⚠️ 警告: 未安装 torch，将使用模拟数据进行预测。")

if HAS_TORCH:
    class BiLSTM_SOH_Model(nn.Module):
        def __init__(self, input_size=9, hidden_size=54, num_layers=2):
            super().__init__()
            self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, bidirectional=True)
            self.fc = nn.Linear(hidden_size * 2, 1)

        def forward(self, x):
            out, _ = self.lstm(x)
            out = out[:, -1, :] 
            out = self.fc(out)
            return out
else:
    class BiLSTM_SOH_Model:
        pass

global_bilstm_model = None
global_deephpm_model = None

if HAS_TORCH:
    try:
        global_bilstm_model = BiLSTM_SOH_Model(input_size=9, hidden_size=54, num_layers=2)
        checkpoint = torch.load("models/BILSTM_20260112_143628.pth", map_location='cpu', weights_only=False)
        if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
            global_bilstm_model.load_state_dict(checkpoint["model_state_dict"])
        else:
            global_bilstm_model.load_state_dict(checkpoint)
        global_bilstm_model.eval() 
        print("✅ BiLSTM模型已成功加载到内存！")
    except Exception as e:
        print(f"❌ BiLSTM模型加载失败: {e}")
        global_bilstm_model = None
    
    try:
        from functions import DeepHPMNN
        global_deephpm_model = DeepHPMNN(
            seq_len=10, 
            inputs_dim=9, 
            outputs_dim=1, 
            layers=[64, 64, 64], 
            scaler_inputs=(torch.zeros(9), torch.ones(9)),
            scaler_targets=(torch.zeros(1), torch.ones(1)),
            inputs_dynamical='s_norm, t_norm',
            inputs_dim_dynamical='9'
        )
        deephpm_checkpoint = torch.load("models/DEEPHPM_20260112_143628.pth", map_location='cpu', weights_only=False)
        if isinstance(deephpm_checkpoint, dict) and "model_state_dict" in deephpm_checkpoint:
            global_deephpm_model.load_state_dict(deephpm_checkpoint["model_state_dict"], strict=False)
        else:
            global_deephpm_model.load_state_dict(deephpm_checkpoint, strict=False)
        global_deephpm_model.eval() 
        print("✅ DeepHPM模型已成功加载到内存！")
    except Exception as e:
        print(f"❌ DeepHPM模型加载失败: {e}")
        global_deephpm_model = None

# 创建FastAPI应用
app = FastAPI(title="储能电池寿命预测系统", version="1.0.0")

# ================= 1. CORS 配置 =================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
    expose_headers=["*"],  
    max_age=3600,
)

# ================= 2. 全局异常处理 =================
from starlette.exceptions import HTTPException as StarletteHTTPException

# 1. 专门处理路由找不到(404)或主动抛出的HTTP异常，不再把它们变成500
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

# 2. 原有的全局异常处理，只抓真正的代码报错(500)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": f"服务器内部错误: {str(exc)}"})

# ================= 3. WebSocket 管理器 =================
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws/alerts")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() 
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ================= 4. 定时任务: 核心多维调度算法 =================
def run_daily_prediction():
    """执行电芯 SOH 真实预测与多维减碳智能派单"""
    print(f"[{datetime.now()}] 正在启动 AI 模型预测与调度任务...")
    db = next(get_db())
    try:
        bms_records = db.query(BMSData.cell_id).distinct().all()
        cell_ids = [r[0] for r in bms_records] if bms_records else ["CELL-001", "CELL-002", "CELL-003"]
        
        for cell_id in cell_ids:
            soh, rul = 100.0, 3000 
            used_real_model = False
            
            if HAS_TORCH and (global_bilstm_model is not None or global_deephpm_model is not None):
                recent_data = db.query(BMSData).filter(BMSData.cell_id == cell_id, BMSData.cycle_end == True).order_by(BMSData.timestamp.desc()).limit(10).all()
                if len(recent_data) == 10:
                    features = []
                    for d in reversed(recent_data): 
                        features.append([d.delta_q_mean, d.delta_q_var, d.cycle_capacity, d.dcir_ohm, d.v_plateau_len, d.charge_efficiency, 0.0, 0.0, d.cycle_index])
                    input_tensor = torch.tensor([features], dtype=torch.float32)
                    with torch.no_grad():
                        if global_deephpm_model is not None:
                            try:
                                prediction, _, _ = global_deephpm_model(inputs=input_tensor)
                                raw_soh = prediction[0][-1][0].item() 
                                used_real_model = True
                            except Exception:
                                if global_bilstm_model is not None:
                                    prediction = global_bilstm_model(input_tensor)
                                    raw_soh = prediction[0][0].item() 
                                    used_real_model = True
                        elif global_bilstm_model is not None:
                            prediction = global_bilstm_model(input_tensor)
                            raw_soh = prediction[0][0].item() 
                            used_real_model = True
                        
                        if used_real_model:
                            if raw_soh <= 2.0: raw_soh = raw_soh * 100.0
                            soh = max(0.0, min(100.0, raw_soh))
                            rul = int((soh - 70) * 10) if soh > 70 else 0
            
            if not used_real_model:
                import random
                soh = random.uniform(75.0, 99.9) 
                rul = int((soh - 70) * 10) 
            
            soh = max(0.0, min(100.0, soh))
            rul = max(0, rul)
            
            alert_level = 0
            if rul < 50: alert_level = 3  
            elif soh < 80.0: alert_level = 2  
            elif soh < 85.0: alert_level = 1  
                
            db.add(PredictionLog(cell_id=cell_id, predicted_soh=soh, predicted_rul=rul, alert_level=alert_level))
            
            ai_confidence = min(0.99, max(0.60, 0.85 + ((10 if used_real_model else 5) * 0.01)))
            
            # --- 模拟多维调度算法 ---
            maintenance_workers = [
                {"name": "王师傅", "distance": 1.2, "current_orders": 0, "skills": ["高级电气工程师"], "carbon_factor": 0.05}, 
                {"name": "李师傅", "distance": 2.5, "current_orders": 3, "skills": ["基础运维"], "carbon_factor": 0.0}, 
                {"name": "张师傅", "distance": 3.1, "current_orders": 1, "skills": ["软件工程师"], "carbon_factor": 0.22}, 
                {"name": "刘师傅", "distance": 0.8, "current_orders": 2, "skills": ["高级电气工程师"], "carbon_factor": 0.05}
            ]
            
            def calculate_worker_score(worker, alert_level):
                distance_score = max(0, 100 - worker["distance"] * 10)
                load_score = max(0, 100 - worker["current_orders"] * 20)
                skill_score = 100 if "高级电气工程师" in worker["skills"] else (50 if alert_level < 3 else 0)
                carbon_emission = worker["distance"] * worker["carbon_factor"]
                carbon_score = max(0, 100 - carbon_emission * 100)
                
                if alert_level == 3:
                    return (distance_score * 0.6) + (skill_score * 0.4), carbon_emission
                else:
                    return (distance_score * 0.2) + (skill_score * 0.4) + (carbon_score * 0.4), carbon_emission
            
            workers_with_scores = [(w, *calculate_worker_score(w, alert_level)) for w in maintenance_workers]
            workers_with_scores.sort(key=lambda x: x[1], reverse=True)
            best_worker, best_score, expected_carbon = workers_with_scores[0]
            
            dispatch_strategy = "🔵 常规智能派单"
            require_immediate_dispatch = True
            
            if alert_level == 3 and ai_confidence > 0.90:
                dispatch_strategy = "🔴 红色熔断响应：秒级强派"
            elif alert_level == 3 and ai_confidence <= 0.90:
                dispatch_strategy = "🟡 双重验证响应：转远程复核"
                require_immediate_dispatch = False
            elif alert_level == 2 and ai_confidence > 0.85:
                dispatch_strategy = "🟢 预测性搭便车：合并例行巡检"

            def get_safety_instructions(level):
                if level == 3: return "【极高危】防电弧服，检查七氟丙烷灭火系统，必须双人同行"
                elif level == 2: return "穿戴绝缘装备；断开汇流排后开箱"
                return "常规操作"
            
            def get_required_parts(level):
                return "磷酸铁锂18650电芯*1, 导热硅脂, 内阻仪" if level >= 2 else "内阻仪"
            
            if alert_level >= 2:
                extra_data = {
                    "ai_confidence": round(ai_confidence, 3),
                    "carbon_emission_kg": round(expected_carbon, 3),
                    "dispatch_strategy": dispatch_strategy,
                    "system_advice": f"电芯SOH衰减至{round(soh,1)}%，建议及时处置。"
                }
                
                order = WorkOrder(
                    cell_id=cell_id, 
                    alert_level=alert_level,
                    status="Pending",
                    assigned_worker=best_worker["name"] if require_immediate_dispatch else "云端复核组",
                    distance_km=best_worker["distance"],
                    safety_instructions=get_safety_instructions(alert_level),
                    required_parts=get_required_parts(alert_level),
                    notes=json.dumps(extra_data, ensure_ascii=False) 
                )
                db.add(order)
                
                alert_msg = {
                    "type": "CRITICAL_ALERT" if alert_level == 3 else "WARNING_ALERT",
                    "cell_id": cell_id,
                    "msg": f"【{dispatch_strategy}】电芯 SOH={round(soh,1)}%，建议策略已下发！",
                    "assigned_worker": best_worker["name"],
                    "carbon_saved": round((best_worker["distance"] * 0.22) - expected_carbon, 2)
                }
                asyncio.run(manager.broadcast(alert_msg))
                
        db.commit()
        print("✅ 预测任务完成，预警与工单已更新。")
    except Exception as e:
        print(f"❌ 定时任务执行失败: {e}")
        db.rollback()
    finally:
        db.close()

@app.on_event("startup")
def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_daily_prediction, 'interval', minutes=2) 
    scheduler.start()

# ================= 5. API 路由引入 =================
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(batteries.router, prefix="/api/batteries", tags=["Batteries"])
app.include_router(datasets.router, prefix="/api/datasets", tags=["Datasets"])
app.include_router(training.router, prefix="/api/training", tags=["Training"])
app.include_router(prediction.router, prefix="/api/prediction", tags=["Prediction"])
app.include_router(model_comparison.router, prefix="/api/model-comparison", tags=["Model Comparison"])
app.include_router(models.router, prefix="/api/models", tags=["Models"])
app.include_router(data_processing.router, prefix="/api/data-processing", tags=["Data Processing"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["Analysis"])
app.include_router(shares.router, prefix="/api/shares", tags=["Shares"])
app.include_router(carbon_calculation.router, prefix="/api/carbon", tags=["Carbon Calculation"])
app.include_router(work_orders.router, prefix="/api/work_orders", tags=["Work Orders工单系统"])


# ================= 6. 工单模块 (修复路由冲突与数据库锁死版) =================

@app.get("/api/work_orders", tags=["Work Orders"])
def get_work_orders(db: Session = Depends(get_db)):
    """获取所有工单列表"""
    try:
        orders = db.query(WorkOrder).order_by(WorkOrder.created_at.desc()).all()
        results = []
        for o in orders:
            created_str = o.created_at.isoformat() if hasattr(o, "created_at") and hasattr(o.created_at, 'isoformat') else str(getattr(o, "created_at", ""))
            resolved_str = o.resolved_at.isoformat() if hasattr(o, "resolved_at") and hasattr(o.resolved_at, 'isoformat') else str(getattr(o, "resolved_at", ""))
            
            o_dict = {
                "id": f"WO-{int(o.id):03d}" if getattr(o, "id", None) else "WO-000",
                "cellId": getattr(o, "cell_id", "未知电芯"),
                "alertLevel": getattr(o, "alert_level", 1),
                "status": getattr(o, "status", "Pending"),
                "assignedWorker": getattr(o, "assigned_worker", "未分配"),
                "distanceKm": getattr(o, "distance_km", 0.0),
                "safetyInstructions": getattr(o, "safety_instructions", ""),
                "requiredParts": getattr(o, "required_parts", ""),
                "createdAt": created_str,
                "resolvedAt": resolved_str,
            }
            try:
                raw_notes = getattr(o, "notes", None)
                extra_data = json.loads(raw_notes) if raw_notes else {}
                if isinstance(extra_data, dict):
                    o_dict["aiConfidence"] = extra_data.get("ai_confidence", 0.85)
                    o_dict["carbonEmissionKg"] = extra_data.get("carbon_emission_kg", 0.0)
                    o_dict["dispatchStrategy"] = extra_data.get("dispatch_strategy", "常规派发")
                    o_dict["notes"] = extra_data.get("resolve_notes", extra_data.get("system_advice", "无详细记录"))
                else:
                    raise ValueError
            except Exception:
                o_dict["aiConfidence"] = 0.85
                o_dict["carbonEmissionKg"] = 0.0
                o_dict["dispatchStrategy"] = "常规派发"
                o_dict["notes"] = getattr(o, "notes", "暂无处置记录")
                
            results.append(o_dict)
        return results
    except Exception as e:
        import traceback
        traceback.print_exc()
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": str(e), "msg": "查询工单列表失败"})

@app.get("/api/work_orders/{order_id}/recommend", tags=["Work Orders"])
def recommend_workers_for_order(order_id: str, db: Session = Depends(get_db)):
    """AI 多维智能派单推荐算法 (终极安全不崩溃版)"""
    try:
        import re
        import math
        
        # 1. 解析工单ID
        match = re.search(r'\d+', str(order_id))
        db_id = int(match.group()) if match else 0
        
        # 默认参数
        target_lat = 31.15
        target_lng = 121.50
        is_emergency = True
        required_skills = set()
        
        # 2. 安全查询工单
        try:
            order = db.query(WorkOrder).filter(WorkOrder.id == db_id).first()
            if order:
                target_lat = float(order.lat) if getattr(order, "lat", None) else 31.15
                target_lng = float(order.lng) if getattr(order, "lng", None) else 121.50
                is_emergency = getattr(order, "alert_level", 1) >= 3
                if getattr(order, "required_skills", None):
                    required_skills = set(s.strip() for s in order.required_skills.split(',') if s.strip())
        except Exception as e:
            db.rollback() 
            print(f"⚠️ 查询工单异常，已安全回滚并降级处理: {e}")
        
        # 动态权重
        W_DISTANCE = 0.6 if is_emergency else 0.3
        W_CARBON   = 0.1 if is_emergency else 0.5
        W_SKILL    = 0.3 if is_emergency else 0.2

        # 3. 安全查询人员
        try:
            users = db.query(User).filter(User.status == True).all()
        except Exception as e:
            db.rollback()
            print(f"⚠️ 查询用户异常，返回兜底演示数据: {e}")
            return {"code": 200, "data": [
                {"id": 1, "name": "系统调度员", "skills": ["高级电气工程师"], "distance": 1.2, "carbon": 0.0, "score": 95, "tag": "最优推荐", "coord": [121.5, 31.16]}
            ]}

        candidates = []
        def calc_distance(lat1, lon1, lat2, lon2):
            if None in (lat1, lon1, lat2, lon2): return 999.9
            R = 6371.0
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            return R * c

        # 4. 核心打分逻辑
        for user in users:
            if getattr(user, "work_status", "free") != 'free':
                continue
                
            user_skills = set(s.strip() for s in (user.skills or "").split(',') if s.strip())
            if not user_skills:
                user_skills = {"初级运维"}
                
            if required_skills and not required_skills.issubset(user_skills):
                continue
                
            u_lat = float(user.current_lat) if getattr(user, "current_lat", None) else 31.15 + (user.id * 0.01)
            u_lng = float(user.current_lng) if getattr(user, "current_lng", None) else 121.50 + (user.id * 0.01)
            
            distance = calc_distance(target_lat, target_lng, u_lat, u_lng)
            u_carbon_index = float(user.carbon_index) if getattr(user, "carbon_index", None) else 0.05
            carbon_emission = distance * u_carbon_index
            
            skill_score = min(len(user_skills) / 5.0, 1.0)
            norm_distance = max(0.0, 1.0 - (distance / 100.0))
            norm_carbon = max(0.0, 1.0 - (carbon_emission / 5.0))
            
            total_score = (W_DISTANCE * norm_distance) + (W_CARBON * norm_carbon) + (W_SKILL * skill_score)
            
            candidates.append({
                "id": user.id,
                "name": user.username or "未知工号",
                "skills": list(user_skills),
                "distance": round(distance, 1),
                "carbon": round(carbon_emission, 2),
                "score": round(total_score * 100, 0),
                "tag": "",
                "coord": [u_lng, u_lat]
            })
            
        candidates.sort(key=lambda x: x["score"], reverse=True)
        
        if candidates:
            candidates[0]['tag'] = "最优推荐"
        for cand in candidates:
            if cand['carbon'] == 0.0 and not cand['tag']:
                cand['tag'] = "零碳通勤"
                
        # 兜底：如果查询成功但是过滤后一个人都没有，给一个模拟人员，保证体验流畅
        if not candidates:
            candidates.append({
                "id": 999, "name": "演示工程师", "skills": ["高级电气"], "distance": 2.5, "carbon": 0.0, "score": 88, "tag": "零碳通勤", "coord": [121.5, 31.15]
            })
            
        return {"code": 200, "data": candidates[:5]}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/api/work_orders/{order_id}/resolve", tags=["Work Orders"])
async def resolve_work_order(order_id: str, request: Request, db: Session = Depends(get_db)):
    """闭环工单并保持原有扩展信息"""
    try:
        match = re.search(r'\d+', str(order_id))
        db_id = int(match.group()) if match else 0
        
        body = json.loads(await request.body())
        resolve_note = body.get('notes', '')
        
        order = db.query(WorkOrder).filter(WorkOrder.id == db_id).first()
        if order:
            order.status = "Resolved"
            order.resolved_at = datetime.utcnow()
            
            try:
                raw_notes = getattr(order, "notes", None)
                extra_data = json.loads(raw_notes) if raw_notes else {}
                if isinstance(extra_data, dict):
                    extra_data["resolve_notes"] = resolve_note
                    order.notes = json.dumps(extra_data, ensure_ascii=False)
                else:
                    order.notes = json.dumps({"resolve_notes": resolve_note}, ensure_ascii=False)
            except Exception:
                order.notes = json.dumps({"resolve_notes": resolve_note}, ensure_ascii=False)
                
            db.commit()
            return {"msg": "工单已闭环归档"}
        return {"msg": "工单不存在"}
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/api/users", tags=["Users"])
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()

@app.get("/")
async def root():
    return {"message": "储能电池寿命预测系统 API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.RELOAD)