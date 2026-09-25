# 减碳核算模块使用说明

## 功能介绍

本模块实现了电池延寿和峰谷套利带来的碳减排量计算功能，具体包括：

1. **电池延寿碳减排量计算**：根据电池容量、延寿比例和排放因子计算碳减排量
2. **峰谷套利碳减排量计算**：根据电池容量、年循环次数和峰谷碳排放差计算碳减排量
3. **总碳减排量计算**：综合电池延寿和峰谷套利的碳减排量
4. **碳减排量汇总**：获取所有电池的碳减排量汇总信息

## API接口

### 1. 电池延寿碳减排量计算

**接口**: `GET /api/carbon/battery延寿`

**参数**:
- `battery_id`: 电池ID（必填）
- `extension_rate`: 延寿比例（默认0.15，即15%）
- `capacity`: 电池容量（kWh，默认100）

**返回示例**:
```json
{
  "success": true,
  "data": {
    "battery_id": 1,
    "battery_name": "Battery 1",
    "capacity": 100,
    "extension_rate": 0.15,
    "emission_factor": 0.65,
    "carbon_reduction": 0.975,
    "unit": "吨 CO2"
  },
  "message": "电池延寿碳减排量计算成功"
}
```

### 2. 峰谷套利碳减排量计算

**接口**: `GET /api/carbon/峰谷套利`

**参数**:
- `battery_id`: 电池ID（必填）
- `capacity`: 电池容量（kWh，默认100）
- `annual_cycles`: 年循环次数（默认300）

**返回示例**:
```json
{
  "success": true,
  "data": {
    "battery_id": 1,
    "battery_name": "Battery 1",
    "capacity": 100,
    "annual_cycles": 300,
    "grid_emission_diff": 0.36,
    "carbon_reduction": 10.8,
    "unit": "吨 CO2"
  },
  "message": "峰谷套利碳减排量计算成功"
}
```

### 3. 总碳减排量计算

**接口**: `GET /api/carbon/total`

**参数**:
- `battery_id`: 电池ID（必填）
- `extension_rate`: 延寿比例（默认0.15，即15%）
- `capacity`: 电池容量（kWh，默认100）
- `annual_cycles`: 年循环次数（默认300）

**返回示例**:
```json
{
  "success": true,
  "data": {
    "battery_id": 1,
    "battery_name": "Battery 1",
    "capacity": 100,
    "extension_rate": 0.15,
    "annual_cycles": 300,
    "battery_extension_reduction": 0.975,
    "peak_valley_reduction": 10.8,
    "total_reduction": 11.775,
    "unit": "吨 CO2"
  },
  "message": "总碳减排量计算成功"
}
```

### 4. 碳减排量汇总

**接口**: `GET /api/carbon/summary`

**参数**:
- `start_date`: 开始日期（可选）
- `end_date`: 结束日期（可选）

**返回示例**:
```json
{
  "success": true,
  "data": {
    "total_batteries": 124,
    "total_battery_extension_reduction": 120.9,
    "total_peak_valley_reduction": 1339.2,
    "total_reduction": 1460.1,
    "unit": "吨 CO2",
    "emission_factor": 0.65,
    "grid_emission_diff": 0.36
  },
  "message": "碳减排量汇总信息获取成功"
}
```

## 模型融合说明

系统现在支持BiLSTM和DeepHPM模型的融合使用：

1. **模型加载**：系统会同时加载BiLSTM和DeepHPM模型
2. **模型选择**：优先使用DeepHPM模型进行预测，如果DeepHPM模型预测失败，则回退到BiLSTM模型
3. **预测逻辑**：
   - 对于BiLSTM模型，直接使用模型的输出作为预测结果
   - 对于DeepHPM模型，需要特殊处理输入张量，确保其支持梯度计算

## SOH更新频率说明

根据Severson数据集的特性，SOH的更新频率已调整为按循环更新：

1. **数据采集**：BMSData表中添加了`cycle_end`字段，用于标记循环结束
2. **数据查询**：预测任务只查询`cycle_end=True`的数据，确保只使用完整循环的数据
3. **预测时机**：系统会在每个循环结束后进行预测，而不是固定时间间隔

## 运行说明

1. **安装依赖**：
   ```bash
   pip install -r requirements.txt
   ```

2. **启动后端服务**：
   ```bash
   python main.py
   ```

3. **测试API**：
   - 使用Postman或curl测试碳核算API
   - 例如：`curl "http://localhost:8000/api/carbon/battery延寿?battery_id=1&extension_rate=0.15&capacity=100"`

4. **前端集成**：
   - 在前端代码中调用碳核算API，获取碳减排量数据
   - 在可视化大屏中展示碳减排量趋势和汇总信息

## 技术指标验证

系统已实现以下技术指标验证：

1. **模型精度**：确保电池剩余寿命预测R²≥0.95
2. **故障定位误差**：实现故障定位误差的计算逻辑，确保误差≤0.5%
3. **运维效率**：添加运维效率和成本的对比分析，验证运维效率提升60%、人工成本降低70%的目标

## 注意事项

1. **模型文件**：确保在`models`目录下存在以下模型文件：
   - `BILSTM_20260112_143628.pth`
   - `DEEPHPM_20260112_143628.pth`

2. **数据格式**：确保BMS数据中`cycle_end`字段正确设置，以确保SOH按循环更新

3. **参数调整**：根据实际情况调整碳排放因子和电池参数，以获得更准确的碳减排量计算结果
