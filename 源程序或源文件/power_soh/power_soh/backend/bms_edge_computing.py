import time
import random
import numpy as np
from scipy.interpolate import interp1d
from sqlalchemy.orm import Session
from db.database import SessionLocal, engine, Base
from db.models import BMSData

# 确保表存在
Base.metadata.create_all(bind=engine)

# =====================================================================
# 第一部分：真实物理规律的底层 BMS 秒级原始数据模拟 (Raw Time-Series)
# =====================================================================
def generate_raw_cycle_data(cycle_index, nominal_capacity=1.1):
    """
    模拟一次完整的恒流放电过程的秒级数据。
    随着 cycle_index(循环次数) 的增加，模拟电池的物理衰减（极化增加、容量衰减）。
    """
    # 1. 模拟电池衰减参数
    degradation = cycle_index / 3000.0  # 假设3000次报废
    actual_capacity = min(nominal_capacity, max(0.8, nominal_capacity - degradation * 0.3) + random.uniform(-0.005, 0.005))
    internal_resistance = 0.015 + degradation * 0.01 + random.uniform(0, 0.002)
    
    # 2. 模拟放电过程 (从 3.6V 放电到 2.0V)
    # LFP 电池特有的放电电压曲线（带平台期）
    # 使用 sigmoid/tanh 函数的变体来拟合磷酸铁锂曲线
    q_array = np.linspace(0, actual_capacity, 200) # 放出的容量序列
    
    raw_data = []
    for q in q_array:
        soc = 1.0 - (q / actual_capacity) # SOC 从 100% 降到 0%
        
        # 核心物理公式：开路电压(OCV) - 极化内阻压降(I*R)
        # 磷酸铁锂 OCV 曲线模拟
        ocv = 3.2 + 0.2 * np.tanh(10 * (soc - 0.5)) + 0.2 * (soc**3)
        if soc < 0.1: ocv -= 10 * (0.1 - soc)**2 # 尾部快速掉电
        
        # 恒流放电 1C (1.1A)
        current = -1.1 
        # 实际端电压
        voltage = ocv + current * internal_resistance
        voltage = max(2.0, min(3.6, voltage)) # 截断在保护电压内
        
        # 模拟温度上升
        temperature = 25.0 + (q / actual_capacity) * 10.0 + random.uniform(-0.5, 0.5)
        
        raw_data.append({
            "voltage": voltage,
            "current": current,
            "capacity": q,
            "temperature": temperature
        })
        
    return raw_data, actual_capacity, internal_resistance

# =====================================================================
# 第二部分：论文级特征提取算法 (Data Preprocessing & Feature Extraction)
# =====================================================================
def extract_features_from_raw(raw_data, baseline_q_interp=None):
    """
    输入：单次循环的秒级原始数据列表
    输出：提取出的 6 大核心高级特征 (对齐 Severson 论文)
    """
    # 1. 提取序列为 Numpy 数组
    v_arr = np.array([d["voltage"] for d in raw_data])
    q_arr = np.array([d["capacity"] for d in raw_data])
    
    # 【预处理算法】：剔除异常噪点 (保证电压单调递减，以便插值)
    # 真实情况数据会震荡，必须使用排序或滤波
    sort_idx = np.argsort(v_arr)[::-1] # 降序排列
    v_clean = v_arr[sort_idx]
    q_clean = q_arr[sort_idx]
    
    # 确保没有重复的电压点，否则插值函数会报错
    v_unique, unique_indices = np.unique(v_clean, return_index=True)
    q_unique = q_clean[unique_indices]
    
    # 【核心特征计算算法】：DeltaQ
    # 建立固定的电压网格 (Voltage Grid)，例如 2.0V 到 3.5V，取 100 个点
    v_grid = np.linspace(2.2, 3.4, 100) 
    
    # 构造插值函数 (Scipy 线性插值)
    f_interp = interp1d(v_unique, q_unique, bounds_error=False, fill_value="extrapolate")
    q_interp = f_interp(v_grid) # 当前循环在标准电压网格下的容量曲线
    
    delta_q_mean = 0.0
    delta_q_var = 0.0
    
    if baseline_q_interp is not None:
        # 计算 Delta Q (当前曲线与基准曲线的差值)
        delta_q_curve = q_interp - baseline_q_interp
        delta_q_mean = np.mean(delta_q_curve)
        delta_q_var = np.var(delta_q_curve)
    else:
        # 如果是第一次运行，这就是基准曲线
        baseline_q_interp = q_interp
    
    # 【其他特征计算】
    # 1. 放电平台长度 (电压在 3.1V 到 3.3V 之间放出的容量)
    plateau_mask = (v_arr >= 3.1) & (v_arr <= 3.3)
    v_plateau_len = np.max(q_arr[plateau_mask]) - np.min(q_arr[plateau_mask]) if np.any(plateau_mask) else 0.0
    
    # 2. 放电容量 (最后一点的容量)
    cycle_capacity = np.max(q_arr)
    
    # 返回提取的高阶特征和基准曲线
    features = {
        "delta_q_mean": float(delta_q_mean),
        "delta_q_var": float(delta_q_var),
        "cycle_capacity": float(cycle_capacity),
        "v_plateau_len": float(v_plateau_len),
        "charge_efficiency": random.uniform(0.95, 0.99) # 简化模拟
    }
    return features, q_interp

# =====================================================================
# 第三部分：主控程序 (打通从端侧到底层数据库的完整流)
# =====================================================================
def run_edge_computing_simulator():
    db = SessionLocal()
    cells = ["CELL-001", "CELL-002", "CELL-003"]
    cycle_counts = {cell: random.randint(50, 150) for cell in cells}
    baseline_curves = {cell: None for cell in cells}
    
    print("🚀 启动 BMS 边缘计算网关模拟器...")
    print("底层逻辑: 生成秒级时序 -> 数据插值清洗 -> 提取高级特征 -> 推送云端")
    
    try:
        while True:
            for cell in cells:
                cycle_counts[cell] += 1
                current_cycle = cycle_counts[cell]
                
                # Step 1: 传感器采集到底层秒级时序数据
                raw_data, _, dcir_ohm = generate_raw_cycle_data(current_cycle)
                
                # Step 2: 边缘网关(Edge)运行特征提取算法
                features, new_baseline = extract_features_from_raw(raw_data, baseline_curves[cell])
                
                # 如果是第一轮，初始化基准曲线
                if baseline_curves[cell] is None:
                    baseline_curves[cell] = new_baseline
                    continue # 第一轮没有 DeltaQ，跳过入库
                
                # Step 3: 将提取好的特征推送到数据库，供深度学习调用
                data = BMSData(
                    cell_id=cell,
                    cycle_index=current_cycle,
                    delta_q_mean=features["delta_q_mean"],
                    delta_q_var=features["delta_q_var"],
                    cycle_capacity=features["cycle_capacity"],
                    dcir_ohm=float(dcir_ohm),
                    v_plateau_len=features["v_plateau_len"],
                    charge_efficiency=features["charge_efficiency"]
                )
                db.add(data)
            
            db.commit()
            print(f"[{time.strftime('%H:%M:%S')}] 边缘计算完成：从原始时序成功提取 6 大高级特征，已推送至云端。")
            time.sleep(10) # 模拟循环等待
            
    except KeyboardInterrupt:
        print("停止模拟。")
    finally:
        db.close()

if __name__ == "__main__":
    # 首次运行需要安装 scipy
    # pip install scipy
    run_edge_computing_simulator()