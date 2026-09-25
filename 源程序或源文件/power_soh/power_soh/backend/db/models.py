from sqlalchemy import (
    Column, Integer, String, Float, 
    DateTime, Boolean, Text, ForeignKey, Enum, Date, BigInteger, DECIMAL
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from db.database import Base
import enum


class User(Base):
    """
    用户表
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="user", nullable=False)  # user: 普通用户, admin: 管理员
    status = Column(Boolean, default=True, nullable=False)  # True: active, False: inactive
    
    # === 核心修复：新增 AI 派单与减碳所需的运维人员特征字段 ===
    skills = Column(String(255), default="初级运维", comment="人员技能标签(逗号分隔)")
    current_lat = Column(DECIMAL(10, 6), default=31.150000, comment="当前纬度")
    current_lng = Column(DECIMAL(10, 6), default=121.500000, comment="当前经度")
    carbon_index = Column(Float, default=0.05, comment="通勤碳排指数(电车为0)")
    work_status = Column(String(20), default="free", comment="工作状态(free/busy)")
    # =======================================================
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), 
        onupdate=func.now(), 
        server_default=func.now()
    )
    
    # 关系
    models = relationship("Model", back_populates="owner")
    training_records = relationship("TrainingRecord", back_populates="creator")
    prediction_records = relationship(
        "PredictionRecord", 
        back_populates="creator"
    )
    datasets = relationship("Dataset", back_populates="owner")
    model_comparisons = relationship(
        "ModelComparison", 
        back_populates="creator"
    )
    # 分享关系（我分享出去的资源）
    shares_sent = relationship("Share", foreign_keys="Share.owner_id", back_populates="owner")
    # 接收到的分享（我被分享的资源）
    shares_received = relationship("Share", foreign_keys="Share.shared_with_user_id", back_populates="shared_with_user")


class BatteryStatus(str, enum.Enum):
    """电池状态枚举"""
    active = "active"
    retired = "retired"
    testing = "testing"


class DatasetType(str, enum.Enum):
    """数据集类型枚举"""
    train = "train"
    validation = "validation"
    test = "test"


class BatteryInfo(Base):
    """
    电池基本信息表 (124组电池)
    """
    __tablename__ = "battery_info"
    
    battery_id = Column(Integer, primary_key=True)  # 电池组编号 (1-124)
    battery_name = Column(String(100), nullable=False, index=True)
    manufacturer = Column(String(100), default="Severson Lab")
    model = Column(String(50), default="LFP/Graphite")
    rated_capacity = Column(DECIMAL(10, 4), default=1.1)
    rated_voltage = Column(DECIMAL(10, 4), default=3.3)
    manufacture_date = Column(Date)
    first_use_date = Column(Date)
    status = Column(Enum(BatteryStatus), default=BatteryStatus.active, index=True)
    dataset_type = Column(Enum(DatasetType), nullable=False, index=True)
    total_cycles = Column(Integer, default=0)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), 
        onupdate=func.now(), 
        server_default=func.now()
    )
    
    # 关系
    lifecycle_data = relationship("BatteryLifecycleData", back_populates="battery")
    statistics = relationship("DataStatistics", back_populates="battery", uselist=False)
    prediction_records = relationship("PredictionRecord", back_populates="battery")


class BatteryLifecycleData(Base):
    """
    电池生命周期数据表 (来自 SeversonBattery.mat)
    """
    __tablename__ = "battery_lifecycle_data"
    
    id = Column(BigInteger, primary_key=True, index=True)
    battery_id = Column(Integer, ForeignKey("battery_info.battery_id", ondelete="CASCADE"), nullable=False, index=True)
    cycle_count = Column(Integer, nullable=False, index=True)
    
    # 8项特征数据 (来自 Features_mov_Flt)
    voltage = Column(DECIMAL(10, 4), nullable=False)
    current = Column(DECIMAL(10, 4), nullable=False)
    temperature = Column(DECIMAL(10, 4), nullable=False)
    capacity = Column(DECIMAL(10, 4), nullable=False)
    resistance = Column(DECIMAL(10, 4), nullable=False)
    soc = Column(DECIMAL(10, 4), nullable=False)
    soh = Column(DECIMAL(10, 4), nullable=False, index=True)
    power = Column(DECIMAL(10, 4), nullable=False)
    
    # 预测目标 (来自 SeversonBattery.mat)
    rul = Column(Integer, nullable=False, index=True)
    pcl = Column(DECIMAL(10, 4), nullable=False, index=True)
    
    # 时间戳
    test_timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    battery = relationship("BatteryInfo", back_populates="lifecycle_data")


class Model(Base):
    """
    模型表 (用户创建的模型)
    """
    __tablename__ = "models"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    algorithm_type = Column(String(50), nullable=False, index=True)
    framework = Column(String(50), default="PyTorch", nullable=False, index=True)
    description = Column(Text)
    hyperparameters = Column(Text)  # 超参数 JSON字符串
    architecture = Column(Text)  # 网络架构 JSON字符串
    input_shape = Column(Text)  # 输入形状 JSON字符串
    output_shape = Column(Text)  # 输出形状 JSON字符串
    metrics = Column(Text)  # 评估指标 JSON字符串
    trained_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    status = Column(String(20), default="completed", nullable=False, index=True)
    model_path = Column(String(255))
    checkpoint_path = Column(String(255))
    model_size = Column(Integer)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), 
        onupdate=func.now(), 
        server_default=func.now()
    )
    
    # 关系
    owner = relationship("User", back_populates="models")
    training_records = relationship("TrainingRecord", back_populates="model")
    prediction_records = relationship(
        "PredictionRecord", 
        back_populates="model"
    )


class TrainingRecord(Base):
    """
    训练记录表
    """
    __tablename__ = "training_records"
    
    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    model_id = Column(Integer, ForeignKey("models.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_path = Column(String(255), nullable=False)
    training_config = Column(Text)  # 训练配置 JSON字符串
    optimizer = Column(String(50))
    learning_rate = Column(Float)
    batch_size = Column(Integer)
    epochs = Column(Integer)
    start_time = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    end_time = Column(DateTime(timezone=True))
    duration = Column(Float)
    initial_loss = Column(Float)
    final_loss = Column(Float)
    best_val_loss = Column(Float)
    convergence_epoch = Column(Integer)
    train_metrics = Column(Text)  # 训练指标 JSON字符串
    validation_metrics = Column(Text)  # 验证指标 JSON字符串
    test_metrics = Column(Text)  # 测试指标 JSON字符串
    parameters_count = Column(Integer)
    memory_usage = Column(Float)
    gpu_usage = Column(Float)
    cpu_usage = Column(Float)
    status = Column(String(20), default="running", nullable=False, index=True)
    logs = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    creator = relationship("User", back_populates="training_records")
    model = relationship("Model", back_populates="training_records")


class PredictionType(str, enum.Enum):
    """预测类型枚举"""
    soh = "soh"
    rul = "rul"
    pcl = "pcl"
    both = "both"


class PredictionRecord(Base):
    """
    预测记录表
    """
    __tablename__ = "prediction_records"
    
    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    model_id = Column(Integer, ForeignKey("models.id", ondelete="CASCADE"), nullable=False, index=True)
    battery_id = Column(Integer, ForeignKey("battery_info.battery_id", ondelete="CASCADE"), nullable=False, index=True)
    input_data = Column(Text)  # 输入数据 JSON字符串
    predicted_soh = Column(Float)
    predicted_rul = Column(Float)
    predicted_pcl = Column(Float)
    actual_soh = Column(Float)
    actual_rul = Column(Float)
    actual_pcl = Column(Float)
    prediction_time = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    execution_time = Column(Float)
    confidence = Column(Float)
    error_analysis = Column(Text)  # 误差分析 JSON字符串
    prediction_type = Column(String(20), default="soh", nullable=False, index=True)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    creator = relationship("User", back_populates="prediction_records")
    model = relationship("Model", back_populates="prediction_records")
    battery = relationship("BatteryInfo", back_populates="prediction_records")


class Dataset(Base):
    """
    数据集表
    """
    __tablename__ = "datasets"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text)
    file_path = Column(String(255), nullable=False)
    file_size = Column(Integer)
    num_samples = Column(Integer)
    feature_columns = Column(Text)  # 特征列名 JSON字符串
    target_columns = Column(Text)  # 目标列名 JSON字符串
    data_format = Column(String(20), default="csv", nullable=False, index=True)
    preprocessing_steps = Column(Text)  # 预处理步骤 JSON字符串
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), 
        onupdate=func.now(), 
        server_default=func.now()
    )
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # 关系
    owner = relationship("User", back_populates="datasets")


class ModelComparison(Base):
    """
    模型比较表
    """
    __tablename__ = "model_comparisons"
    
    id = Column(Integer, primary_key=True, index=True)
    comparison_name = Column(String(100), nullable=False, index=True)
    compared_models = Column(Text)  # 参与比较的模型 IDs JSON字符串
    comparison_metrics = Column(Text)  # 比较指标 JSON字符串
    comparison_results = Column(Text)  # 比较结果 JSON字符串
    statistical_tests = Column(Text)  # 统计检验结果 JSON字符串
    visualization_data = Column(Text)  # 可视化数据 JSON字符串
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), 
        onupdate=func.now(), 
        server_default=func.now()
    )
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # 关系
    creator = relationship("User", foreign_keys=[created_by], back_populates="model_comparisons")


class DataStatistics(Base):
    """
    数据统计表
    """
    __tablename__ = "data_statistics"
    
    stat_id = Column(Integer, primary_key=True, index=True)
    battery_id = Column(Integer, ForeignKey("battery_info.battery_id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # 电压统计
    voltage_mean = Column(DECIMAL(10, 4))
    voltage_variance = Column(DECIMAL(10, 4))
    voltage_min = Column(DECIMAL(10, 4))
    voltage_max = Column(DECIMAL(10, 4))
    voltage_std = Column(DECIMAL(10, 4))
    
    # 电流统计
    current_mean = Column(DECIMAL(10, 4))
    current_variance = Column(DECIMAL(10, 4))
    current_min = Column(DECIMAL(10, 4))
    current_max = Column(DECIMAL(10, 4))
    current_std = Column(DECIMAL(10, 4))
    
    # 温度统计
    temperature_mean = Column(DECIMAL(10, 4))
    temperature_variance = Column(DECIMAL(10, 4))
    temperature_min = Column(DECIMAL(10, 4))
    temperature_max = Column(DECIMAL(10, 4))
    temperature_std = Column(DECIMAL(10, 4))
    
    # 容量统计
    capacity_mean = Column(DECIMAL(10, 4))
    capacity_variance = Column(DECIMAL(10, 4))
    capacity_min = Column(DECIMAL(10, 4))
    capacity_max = Column(DECIMAL(10, 4))
    capacity_std = Column(DECIMAL(10, 4))
    
    # 内阻统计
    resistance_mean = Column(DECIMAL(10, 4))
    resistance_variance = Column(DECIMAL(10, 4))
    resistance_min = Column(DECIMAL(10, 4))
    resistance_max = Column(DECIMAL(10, 4))
    resistance_std = Column(DECIMAL(10, 4))
    
    # SOC统计
    soc_mean = Column(DECIMAL(10, 4))
    soc_variance = Column(DECIMAL(10, 4))
    soc_min = Column(DECIMAL(10, 4))
    soc_max = Column(DECIMAL(10, 4))
    soc_std = Column(DECIMAL(10, 4))
    
    # SOH统计
    soh_mean = Column(DECIMAL(10, 4))
    soh_variance = Column(DECIMAL(10, 4))
    soh_min = Column(DECIMAL(10, 4))
    soh_max = Column(DECIMAL(10, 4))
    soh_std = Column(DECIMAL(10, 4))
    
    # 功率统计
    power_mean = Column(DECIMAL(10, 4))
    power_variance = Column(DECIMAL(10, 4))
    power_min = Column(DECIMAL(10, 4))
    power_max = Column(DECIMAL(10, 4))
    power_std = Column(DECIMAL(10, 4))
    
    # RUL和PCL统计
    rul_mean = Column(DECIMAL(10, 4))
    rul_min = Column(Integer)
    rul_max = Column(Integer)
    rul_std = Column(DECIMAL(10, 4))
    
    pcl_mean = Column(DECIMAL(10, 4))
    pcl_min = Column(DECIMAL(10, 4))
    pcl_max = Column(DECIMAL(10, 4))
    pcl_std = Column(DECIMAL(10, 4))
    
    # 元信息
    total_cycles = Column(Integer)
    data_completeness = Column(DECIMAL(5, 4), default=1.0000)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # 关系
    battery = relationship("BatteryInfo", back_populates="statistics")


class Share(Base):
    """
    资源共享表
    用于用户之间的资源共享（模型、数据集、预测结果等）
    """
    __tablename__ = "shares"
    
    id = Column(Integer, primary_key=True, index=True)
    resource_type = Column(String(50), nullable=False, index=True)  # model/dataset/prediction/training
    resource_id = Column(Integer, nullable=False, index=True)  # 资源的ID
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)  # 资源所有者
    shared_with_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)  # 被分享的用户ID（NULL表示公开分享）
    permission = Column(String(20), default="read", nullable=False)  # read: 只读, write: 读写
    notes = Column(Text)  # 分享备注
    expires_at = Column(DateTime(timezone=True), nullable=True)  # 分享过期时间（可选）
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    is_active = Column(Boolean, default=True, nullable=False, index=True)  # 是否激活
    
    # 关系
    owner = relationship("User", foreign_keys=[owner_id], back_populates="shares_sent")
    shared_with_user = relationship("User", foreign_keys=[shared_with_user_id], back_populates="shares_received")

# ================= 新增：预警与工单模块模型 =================

class BMSData(Base):
    """BMS实时特征数据表 (对齐 Severson 数据集的 Features_mov_Flt)"""
    __tablename__ = "bms_data"
    
    id = Column(Integer, primary_key=True, index=True)
    cell_id = Column(String(50), index=True)  # 电芯编号 (对应 Cell_ID)
    cycle_index = Column(Integer)             # 循环序号 (对应 Cycle_Index)
    cycle_end = Column(Boolean, default=False)  # 循环结束标记，True表示一个完整循环结束
    
    # --- 老师文档要求的 6 大核心老化特征 ---
    delta_q_mean = Column(Float)      # 容量-电压曲线差值均值
    delta_q_var = Column(Float)       # 容量-电压曲线差值方差
    cycle_capacity = Column(Float)    # 当前循环放电容量
    dcir_ohm = Column(Float)          # 直流内阻
    v_plateau_len = Column(Float)     # 放电平台长度
    charge_efficiency = Column(Float) # 充电效率
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class PredictionLog(Base):
    """模型每日预测预警记录表"""
    __tablename__ = "prediction_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    cell_id = Column(String(50), index=True)
    predicted_soh = Column(Float) # 预测的SOH (0-100)
    predicted_rul = Column(Integer) # 预测剩余循环寿命
    alert_level = Column(Integer, default=0) # 0:正常, 1:一级, 2:二级, 3:三级
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class WorkOrder(Base):
    """运维工单表"""
    __tablename__ = "work_orders"
    
    id = Column(Integer, primary_key=True, index=True)
    cell_id = Column(String(50))
    alert_level = Column(Integer) # 报警级别(2或3才生成工单)
    status = Column(String(20), default="Pending") # Pending待处理, Resolved已解决
    assigned_worker = Column(String(100), nullable=True) # 派送给谁（姓名）
    distance_km = Column(Float, nullable=True) # 距离
    safety_instructions = Column(Text, nullable=True) # 安全提示内容
    required_parts = Column(Text, nullable=True) # 所需备件
    image_url = Column(String(255), nullable=True) # 现场处置照片URL
    notes = Column(Text, nullable=True) # 处置记录
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    # --- 新增映射数据库中位置与技能字段 ---
    lat = Column(DECIMAL(10, 6), default=31.150000, comment='故障点纬度')
    lng = Column(DECIMAL(10, 6), default=121.500000, comment='故障点经度')
    required_skills = Column(String(255), default='', comment='所需技能')
    required_certifications = Column(String(255), default='', comment='所需资质')