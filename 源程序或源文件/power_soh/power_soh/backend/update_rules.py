import os

file_path = "main.py"

# 读取当前的 main.py
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 定位要替换的旧预警代码块
old_rules = """            # --- 🚦 预警规则引擎 (对照项目要求) 🚦 ---
            alert_level = 0
            if soh < 80 or rul < 50:
                alert_level = 3  # 三级预警：SOH低于80%，或寿命不足50次
            elif soh < 85:
                alert_level = 2  # 二级预警：SOH低于85%
            elif soh < 90:
                alert_level = 1  # 一级预警：SOH低于90% (轻微衰减)
                
            # 保存预测记录
            log = PredictionLog(cell_id=cell_id, predicted_soh=soh, predicted_rul=rul, alert_level=alert_level)
            db.add(log)
            
            # 生成工单和推送
            if alert_level >= 2:
                order = WorkOrder(cell_id=cell_id, alert_level=alert_level)
                db.add(order)
                
            if alert_level == 3:
                alert_msg = {
                    "type": "CRITICAL_ALERT",
                    "cell_id": cell_id,
                    "soh": round(soh, 2),
                    "rul": rul,
                    "msg": f"紧急！单体电芯 {cell_id} 极度衰减，要求24小时内紧急处置！"
                }
                # 在同步方法中触发异步的 WebSocket 广播
                asyncio.run(manager.broadcast(alert_msg))"""

# 替换为您制定的工业级三级预警新规则
new_rules = """            # --- 🚦 预警规则引擎 (对照最新三级预警规范) 🚦 ---
            alert_level = 0
            if rul < 50:
                alert_level = 3  # 三级预警(严重故障风险)：寿命不足50次
            elif soh < 80.0:
                alert_level = 2  # 二级预警(中度异常)：SOH低于80%
            elif soh < 85.0:
                alert_level = 1  # 一级预警(轻微衰减)：SOH低于85%
                
            # 保存预测记录
            log = PredictionLog(cell_id=cell_id, predicted_soh=soh, predicted_rul=rul, alert_level=alert_level)
            db.add(log)
            
            # 生成工单和推送
            if alert_level == 2:
                # 二级预警：系统自动生成运维工单
                order = WorkOrder(cell_id=cell_id, alert_level=alert_level)
                db.add(order)
                # 弹窗提示运维负责人 (要求 15 天内完成更换)
                alert_msg = {
                    "type": "WARNING_ALERT",
                    "cell_id": cell_id,
                    "soh": round(soh, 2),
                    "rul": rul,
                    "msg": f"【二级预警】电芯 {cell_id} 衰减明显(SOH<80%)，请在 15 天内完成更换！"
                }
                asyncio.run(manager.broadcast(alert_msg))
                
            elif alert_level == 3:
                # 三级预警：系统自动生成紧急工单
                order = WorkOrder(cell_id=cell_id, alert_level=alert_level)
                db.add(order)
                # 立刻弹窗 + 声音告警 (要求 24 小时内紧急处置)
                alert_msg = {
                    "type": "CRITICAL_ALERT",
                    "cell_id": cell_id,
                    "soh": round(soh, 2),
                    "rul": rul,
                    "msg": f"【三级预警】电芯 {cell_id} 寿命不足50次，存在严重故障风险，要求 24 小时内紧急处置！"
                }
                asyncio.run(manager.broadcast(alert_msg))"""

# 执行替换
if old_rules in content:
    content = content.replace(old_rules, new_rules)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ 完美！main.py 中的预警规则已成功升级为您的最新版本！")
else:
    print("⚠️ 未找到旧代码段，可能您已经替换过了，或者代码结构有变。")