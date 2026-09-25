import os
import sys

# 动态导入防止路径问题
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db.database import SessionLocal
from db.models import PredictionLog, BMSData

print("🧹 开始执行全盘数据清洗计划...")
db = SessionLocal()

# 1. 修复预测记录表
try:
    logs = db.query(PredictionLog).filter(PredictionLog.predicted_soh > 100.0).all()
    for log in logs:
        log.predicted_soh = 100.0
    print(f"✅ 成功将 {len(logs)} 条超过 100% 的历史预测记录强制削平为 100.0！")
except Exception as e:
    print(f"清理预测记录表出错: {e}")

# 2. 修复底层特征表 (容量超过额定值会导致前端反推 SOH > 100)
try:
    bms_records = db.query(BMSData).filter(BMSData.cycle_capacity > 1.1).all()
    for b in bms_records:
        b.cycle_capacity = 1.1
    print(f"✅ 成功将 {len(bms_records)} 条容量溢出的底层特征强制削平！")
except Exception as e:
    print(f"清理BMS记录表出错: {e}")

db.commit()
db.close()

# 3. 顺手给生成器代码戴上“紧箍咒”
file_path = "bms_edge_computing.py"
if os.path.exists(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()
    
    old_line = "actual_capacity = max(0.8, nominal_capacity - degradation * 0.3) + random.uniform(-0.005, 0.005)"
    new_line = "actual_capacity = min(nominal_capacity, max(0.8, nominal_capacity - degradation * 0.3) + random.uniform(-0.005, 0.005))"
    
    if old_line in code:
        code = code.replace(old_line, new_line)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
        print("✅ 成功给边缘网关代码打上补丁，未来产生的新数据绝对不会超标了！")

print("🎉 全部清洗完成！")