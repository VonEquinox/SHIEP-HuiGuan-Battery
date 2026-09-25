<template>
  <div class="carbon-calculation-container">
    <el-card shadow="hover" class="main-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">减碳核算模块</span>
          <el-button type="primary" size="small" @click="calculateCarbonReduction" class="calculate-button">
            <el-icon><Document /></el-icon>
            计算碳减排量
          </el-button>
        </div>
      </template>

      <!-- 减碳核算配置 -->
      <div class="section">
        <h3 class="section-title">核算配置</h3>
        <div class="calculation-config">
          <el-form :model="calculationConfig" label-width="150px">
            <el-form-item label="储能系统容量 (kWh)">
              <el-input v-model.number="calculationConfig.capacity" placeholder="请输入储能系统容量" />
            </el-form-item>
            <el-form-item label="电池类型">
              <el-select v-model="calculationConfig.batteryType" placeholder="选择电池类型">
                <el-option label="磷酸铁锂" value="lfp" />
                <el-option label="三元锂" value="ncm" />
                <el-option label="铅酸" value="lead-acid" />
              </el-select>
            </el-form-item>
            <el-form-item label="电池延寿比例 (%)">
              <el-input v-model.number="calculationConfig.lifespanExtension" placeholder="请输入电池延寿比例" />
            </el-form-item>
            <el-form-item label="年循环次数">
              <el-input v-model.number="calculationConfig.cycleCount" placeholder="请输入年循环次数" />
            </el-form-item>
            <el-form-item label="峰谷碳排放差 (kgCO₂/kWh)">
              <el-input v-model.number="calculationConfig.peakValleyEmissionDiff" placeholder="请输入峰谷碳排放差" />
            </el-form-item>
            <el-form-item label="电池碳排放因子 (kgCO₂/kWh)">
              <el-input v-model.number="calculationConfig.batteryEmissionFactor" placeholder="请输入电池碳排放因子" />
            </el-form-item>
          </el-form>
        </div>
      </div>

      <!-- 减碳计算结果 -->
      <div class="section">
        <h3 class="section-title">减碳计算结果</h3>
        <div class="calculation-results">
          <div class="results-grid">
            <div class="result-card">
              <div class="result-title">电池延寿减碳量</div>
              <div class="result-value">{{ batteryLifespanReduction }} 吨 CO₂/年</div>
              <div class="result-description">通过延长电池使用寿命减少的碳排放</div>
            </div>
            <div class="result-card">
              <div class="result-title">峰谷套利减碳量</div>
              <div class="result-value">{{ peakValleyReduction }} 吨 CO₂/年</div>
              <div class="result-description">通过峰谷电价套利减少的电网侧碳排放</div>
            </div>
            <div class="result-card total">
              <div class="result-title">总减碳量</div>
              <div class="result-value">{{ totalReduction }} 吨 CO₂/年</div>
              <div class="result-description">电池延寿与峰谷套利减碳量之和</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 减碳效益分析 -->
      <div class="section">
        <h3 class="section-title">减碳效益分析</h3>
        <div class="benefit-analysis">
          <div class="analysis-grid">
            <!-- 减碳量趋势 -->
            <div class="analysis-card">
              <h4 class="sub-section-title">减碳量趋势</h4>
              <div ref="carbonTrendRef" class="chart" style="height: 300px;"></div>
            </div>
            <!-- 减碳贡献占比 -->
            <div class="analysis-card">
              <h4 class="sub-section-title">减碳贡献占比</h4>
              <div ref="carbonContributionRef" class="chart" style="height: 300px;"></div>
            </div>
            <!-- 减碳经济效益 -->
            <div class="analysis-card">
              <h4 class="sub-section-title">减碳经济效益</h4>
              <el-table :data="economicBenefits" style="width: 100%">
                <el-table-column prop="item" label="项目" />
                <el-table-column prop="value" label="数值" />
                <el-table-column prop="unit" label="单位" />
              </el-table>
            </div>
          </div>
        </div>
      </div>

      <!-- 减碳报告 -->
      <div class="section">
        <h3 class="section-title">减碳报告</h3>
        <div class="carbon-report">
          <el-card shadow="hover" class="report-card">
            <template #header>
              <div class="report-header">
                <span class="report-title">储能系统减碳分析报告</span>
                <el-button type="primary" size="small" @click="exportReport">
                  <el-icon><Download /></el-icon>
                  导出报告
                </el-button>
              </div>
            </template>
            <div class="report-content">
              <h4>一、项目概况</h4>
              <p>储能系统容量：{{ calculationConfig.capacity }} kWh</p>
              <p>电池类型：{{ getBatteryTypeLabel(calculationConfig.batteryType) }}</p>
              <p>电池延寿比例：{{ calculationConfig.lifespanExtension }}%</p>
              <p>年循环次数：{{ calculationConfig.cycleCount }} 次</p>
              
              <h4 style="margin-top: 20px;">二、减碳计算</h4>
              <p>1. 电池延寿减碳量：{{ batteryLifespanReduction }} 吨 CO₂/年</p>
              <p>   计算公式：容量 × 延寿比例 × 排放因子 ÷ 1000</p>
              <p>   计算过程：{{ calculationConfig.capacity }} × {{ calculationConfig.lifespanExtension }}% × {{ calculationConfig.batteryEmissionFactor }} ÷ 1000 = {{ batteryLifespanReduction }} 吨 CO₂/年</p>
              
              <p>2. 峰谷套利减碳量：{{ peakValleyReduction }} 吨 CO₂/年</p>
              <p>   计算公式：容量 × 年循环次数 × 峰谷碳排放差 ÷ 1000</p>
              <p>   计算过程：{{ calculationConfig.capacity }} × {{ calculationConfig.cycleCount }} × {{ calculationConfig.peakValleyEmissionDiff }} ÷ 1000 = {{ peakValleyReduction }} 吨 CO₂/年</p>
              
              <p>3. 总减碳量：{{ totalReduction }} 吨 CO₂/年</p>
              
              <h4 style="margin-top: 20px;">三、环境效益</h4>
              <p>相当于植树：{{ equivalentTrees }} 棵/年</p>
              <p>相当于减少燃油车行驶：{{ equivalentCarMileage }} 公里/年</p>
              <p>相当于节约标准煤：{{ equivalentCoal }} 吨/年</p>
              
              <h4 style="margin-top: 20px;">四、经济效益</h4>
              <p>电池更换成本节约：{{ savedBatteryCost }} 万元/年</p>
              <p>峰谷套利收益：{{ peakValleyProfit }} 万元/年</p>
              <p>总经济效益：{{ totalEconomicBenefit }} 万元/年</p>
            </div>
          </el-card>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, onUnmounted } from 'vue'
import { Document, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import request from '@/utils/request' // 引入已封装的 axios

// 选定操作的电池ID (可根据实际业务扩展为下拉框选择，这里默认1)
const selectedBatteryId = ref(1)

// 核算配置 (作为后端请求的参数)
const calculationConfig = ref({
  capacity: 100, // 储能系统容量（kWh）
  batteryType: 'lfp', 
  lifespanExtension: 15, // 电池延寿比例（%）
  cycleCount: 300, // 年循环次数
})

// 后端返回的计算结果
const batteryLifespanReduction = ref(0) 
const peakValleyReduction = ref(0) 
const totalReduction = ref(0) 
const backendEmissionFactor = ref(0) // 后端返回的碳排放因子常量

// 经济效益 (基于后端碳减排数据衍生计算)
const economicBenefits = ref([
  { item: '电池更换成本节约', value: 0, unit: '万元/年' },
  { item: '峰谷套利收益', value: 0, unit: '万元/年' },
  { item: '总经济效益', value: 0, unit: '万元/年' },
  { item: '投资回收期', value: 0, unit: '年' }
])

// 环境效益
const equivalentTrees = ref(0) 
const equivalentCarMileage = ref(0) 
const equivalentCoal = ref(0) 

const savedBatteryCost = ref(0) 
const peakValleyProfit = ref(0) 
const totalEconomicBenefit = ref(0) 

// 图表引用
const carbonTrendRef = ref(null)
const carbonContributionRef = ref(null)
let carbonTrendChart = null
let carbonContributionChart = null

// 核心：调用后端真实 API 计算碳减排量
const calculateCarbonReduction = async () => {
  try {
    // 调用 backend/api/carbon_calculation.py 中的 /total 接口
    const res = await request.get('/carbon_calculation/total', {
      params: {
        battery_id: selectedBatteryId.value,
        extension_rate: calculationConfig.value.lifespanExtension / 100, // 后端接收小数 0.15
        capacity: calculationConfig.value.capacity,
        annual_cycles: calculationConfig.value.cycleCount
      }
    })

    if (res.data && res.data.success) {
      const data = res.data.data
      // 使用后端计算好的精准数据
      batteryLifespanReduction.value = data.battery_extension_reduction
      peakValleyReduction.value = data.peak_valley_reduction
      totalReduction.value = data.total_reduction
      backendEmissionFactor.value = data.emission_factor || 0.65

      // 同步计算经济和环境效益
      calculateEconomicBenefits()
      calculateEnvironmentalBenefits()
      initCharts()
      
      ElMessage.success('已获取云端最新碳减排核算结果')
    } else {
      ElMessage.error(res.data?.message || '核算失败')
    }
  } catch (error) {
    ElMessage.error('调用减碳计算引擎失败，请检查网络或后端服务')
    console.error(error)
  }
}

// 基于真实减碳数据计算经济效益
const calculateEconomicBenefits = () => {
  const batteryCostPerKwh = 1500
  savedBatteryCost.value = (calculationConfig.value.capacity * batteryCostPerKwh * calculationConfig.value.lifespanExtension / 100 / 10000).toFixed(2)
  const priceDiff = 0.5
  peakValleyProfit.value = (calculationConfig.value.capacity * calculationConfig.value.cycleCount * priceDiff / 10000).toFixed(2)
  totalEconomicBenefit.value = (parseFloat(savedBatteryCost.value) + parseFloat(peakValleyProfit.value)).toFixed(2)
  
  economicBenefits.value = [
    { item: '电池更换成本节约', value: savedBatteryCost.value, unit: '万元/年' },
    { item: '峰谷套利收益', value: peakValleyProfit.value, unit: '万元/年' },
    { item: '总经济效益', value: totalEconomicBenefit.value, unit: '万元/年' },
    { item: '投资回收期', value: (calculationConfig.value.capacity * batteryCostPerKwh / 10000 / parseFloat(totalEconomicBenefit.value)).toFixed(2), unit: '年' }
  ]
}

// 基于真实减碳数据计算环境效益
const calculateEnvironmentalBenefits = () => {
  const totalReductionValue = parseFloat(totalReduction.value)
  equivalentTrees.value = Math.round(totalReductionValue * 1000 / 21.77)
  equivalentCarMileage.value = Math.round(totalReductionValue * 1000 / 0.12)
  equivalentCoal.value = (totalReductionValue / 2.6).toFixed(2)
}

// 真正的导出报告逻辑 (生成 TXT 文件并触发下载)
const exportReport = () => {
  // 1. 动态拼接报告文本内容
  const reportText = `
=============================================
         多园区储能系统减碳分析报告
=============================================
生成时间：${new Date().toLocaleString()}

【一、项目概况】
储能系统容量：${calculationConfig.value.capacity} kWh
电池类型：${getBatteryTypeLabel(calculationConfig.value.batteryType)}
电池延寿比例：${calculationConfig.value.lifespanExtension}%
年循环次数：${calculationConfig.value.cycleCount} 次

【二、减碳计算】
1. 电池延寿减碳量：${batteryLifespanReduction.value} 吨 CO2/年
   (计算过程：${calculationConfig.value.capacity} × ${calculationConfig.value.lifespanExtension}% × ${backendEmissionFactor.value} ÷ 1000)
2. 峰谷套利减碳量：${peakValleyReduction.value} 吨 CO2/年
   (计算过程：${calculationConfig.value.capacity} × ${calculationConfig.value.cycleCount} × ${calculationConfig.value.peakValleyEmissionDiff || 0.36} ÷ 1000)
3. 总减碳量：${totalReduction.value} 吨 CO2/年

【三、环境效益】
相当于植树：${equivalentTrees.value} 棵/年
相当于减少燃油车行驶：${equivalentCarMileage.value} 公里/年
相当于节约标准煤：${equivalentCoal.value} 吨/年

【四、经济效益】
电池更换成本节约：${savedBatteryCost.value} 万元/年
峰谷套利收益：${peakValleyProfit.value} 万元/年
总经济效益：${totalEconomicBenefit.value} 万元/年
=============================================
Powered by BiLSTM + DeepHPM 联合物理信息模型
`;

  // 2. 利用 Blob 将文字转化为文件流
  const blob = new Blob([reportText], { type: 'text/plain;charset=utf-8' });
  const url = window.URL.createObjectURL(blob);
  
  // 3. 创建隐藏的 a 标签，模拟点击下载
  const link = document.createElement('a');
  link.href = url;
  // 设置下载的文件名，带上时间戳
  link.download = `储能减碳分析报告_${new Date().getTime()}.txt`;
  document.body.appendChild(link);
  link.click();
  
  // 4. 清理内存并弹出成功提示
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
  
  ElMessage.success('✅ 报告导出成功，文件已下载到本地！');
}
const getBatteryTypeLabel = (type) => { return { 'lfp': '磷酸铁锂', 'ncm': '三元锂', 'lead-acid': '铅酸' }[type] || type }

// 初始化减碳趋势图 (代码逻辑不变，但数据源已变为后端真实数据)
const initCarbonTrendChart = () => {
  if (!carbonTrendRef.value) return
  if (carbonTrendChart) carbonTrendChart.dispose()
  carbonTrendChart = echarts.init(carbonTrendRef.value)
  
  const years = ['第1年', '第2年', '第3年', '第4年', '第5年']
  const batteryLifespanData = years.map(() => parseFloat(batteryLifespanReduction.value))
  const peakValleyData = years.map(() => parseFloat(peakValleyReduction.value))
  const totalData = years.map((_, index) => batteryLifespanData[index] + peakValleyData[index])
  
  const option = {
    backgroundColor: 'rgba(16, 28, 56, 0.6)', tooltip: { trigger: 'axis' },
    legend: { data: ['电池延寿减碳', '峰谷套利减碳', '总减碳量'], textStyle: { color: '#fff' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: years, axisLabel: { color: '#fff' }, axisLine: { lineStyle: { color: '#00F5FF' } } },
    yAxis: { type: 'value', axisLabel: { color: '#fff', formatter: '{value} 吨' }, axisLine: { lineStyle: { color: '#00F5FF' } }, splitLine: { lineStyle: { color: 'rgba(0, 245, 255, 0.1)' } } },
    series: [
      { name: '电池延寿减碳', type: 'bar', data: batteryLifespanData, itemStyle: { color: '#00F5FF' } },
      { name: '峰谷套利减碳', type: 'bar', data: peakValleyData, itemStyle: { color: '#67C23A' } },
      { name: '总减碳量', type: 'line', data: totalData, lineStyle: { color: '#E6A23C', width: 3 }, itemStyle: { color: '#E6A23C' } }
    ]
  }
  carbonTrendChart.setOption(option)
}

const initCarbonContributionChart = () => {
  if (!carbonContributionRef.value) return
  if (carbonContributionChart) carbonContributionChart.dispose()
  carbonContributionChart = echarts.init(carbonContributionRef.value)
  const option = {
    backgroundColor: 'rgba(16, 28, 56, 0.6)', tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', left: 'left', textStyle: { color: '#fff' } },
    series: [
      {
        name: '减碳贡献', type: 'pie', radius: '70%', center: ['60%', '50%'],
        data: [
          { value: parseFloat(batteryLifespanReduction.value), name: '电池延寿减碳' },
          { value: parseFloat(peakValleyReduction.value), name: '峰谷套利减碳' }
        ],
        emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' } },
        itemStyle: { color: (params) => ['#00F5FF', '#67C23A'][params.dataIndex] }
      }
    ]
  }
  carbonContributionChart.setOption(option)
}

const initCharts = () => { nextTick(() => { initCarbonTrendChart(); initCarbonContributionChart() }) }
const handleResize = () => { carbonTrendChart?.resize(); carbonContributionChart?.resize() }

onMounted(() => {
  calculateCarbonReduction() // 初始化时从后端拉取一次
  window.addEventListener('resize', handleResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  carbonTrendChart?.dispose()
  carbonContributionChart?.dispose()
})
</script>

<style scoped>
.carbon-calculation-container {
  padding: 20px;
  background-color: #0b0f19;
  min-height: 100vh;
  color: #fff;
}

.main-card {
  background: rgba(16, 28, 56, 0.8);
  border: 1px solid rgba(0, 245, 255, 0.3);
  box-shadow: 0 0 20px rgba(0, 102, 255, 0.2);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 18px;
  font-weight: bold;
  color: #00F5FF;
  text-shadow: 0 0 8px rgba(0, 245, 255, 0.5);
}

.calculate-button {
  background: #0066FF;
  border-color: #00F5FF;
  box-shadow: 0 0 10px #0066FF;
}

.section {
  margin-top: 30px;
}

.section-title {
  font-size: 16px;
  font-weight: bold;
  color: #00F5FF;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(0, 245, 255, 0.3);
}

.sub-section-title {
  font-size: 14px;
  font-weight: bold;
  color: #fff;
  margin-bottom: 15px;
}

/* 核算配置 */
.calculation-config {
  background: rgba(16, 28, 56, 0.8);
  border: 1px solid rgba(0, 245, 255, 0.3);
  border-radius: 8px;
  padding: 20px;
}

/* 计算结果 */
.calculation-results {
  background: rgba(16, 28, 56, 0.8);
  border: 1px solid rgba(0, 245, 255, 0.3);
  border-radius: 8px;
  padding: 20px;
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}

.result-card {
  background: rgba(16, 28, 56, 0.8);
  border: 1px solid rgba(0, 245, 255, 0.3);
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  transition: all 0.3s;
}

.result-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 0 20px rgba(0, 245, 255, 0.4);
  border: 1px solid rgba(0, 245, 255, 0.8);
}

.result-card.total {
  background: rgba(103, 194, 58, 0.1);
  border-color: rgba(103, 194, 58, 0.5);
}

.result-title {
  font-size: 14px;
  color: #8898aa;
  margin-bottom: 10px;
}

.result-value {
  font-size: 24px;
  font-weight: bold;
  color: #00F5FF;
  text-shadow: 0 0 10px rgba(0, 245, 255, 0.8);
  margin-bottom: 10px;
}

.result-description {
  font-size: 12px;
  color: #8898aa;
}

/* 减碳效益分析 */
.benefit-analysis {
  background: rgba(16, 28, 56, 0.8);
  border: 1px solid rgba(0, 245, 255, 0.3);
  border-radius: 8px;
  padding: 20px;
}

.analysis-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 20px;
}

.analysis-card {
  background: rgba(16, 28, 56, 0.8);
  border: 1px solid rgba(0, 245, 255, 0.3);
  border-radius: 8px;
  padding: 20px;
}

.chart {
  width: 100%;
  height: 100%;
}

/* 减碳报告 */
.carbon-report {
  background: rgba(16, 28, 56, 0.8);
  border: 1px solid rgba(0, 245, 255, 0.3);
  border-radius: 8px;
  padding: 20px;
}

.report-card {
  background: rgba(16, 28, 56, 0.8);
  border: 1px solid rgba(0, 245, 255, 0.3);
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.report-title {
  font-size: 16px;
  font-weight: bold;
  color: #00F5FF;
}

.report-content {
  line-height: 1.6;
}

.report-content h4 {
  color: #00F5FF;
  margin-bottom: 10px;
}

.report-content p {
  margin-bottom: 8px;
  text-indent: 20px;
}

/* 表格样式 */
:deep(.el-table) {
  background-color: transparent !important;
  color: #fff;
}

:deep(.el-table th.el-table__cell),
:deep(.el-table tr) {
  background-color: transparent !important;
}

:deep(.el-table__row:hover) {
  background-color: rgba(0, 102, 255, 0.1) !important;
}

:deep(.el-table__header-wrapper th) {
  color: #00F5FF !important;
  background-color: rgba(16, 28, 56, 0.8) !important;
}

/* 输入框样式 */
:deep(.el-input__wrapper) {
  background-color: rgba(16, 28, 56, 0.8) !important;
  box-shadow: 0 0 0 1px rgba(0, 245, 255, 0.5) inset !important;
}

:deep(.el-input__inner) {
  color: #00F5FF !important;
}

:deep(.el-select .el-input__inner) {
  color: #00F5FF !important;
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .analysis-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .results-grid {
    grid-template-columns: 1fr;
  }
  
  .calculation-config {
    padding: 15px;
  }
  
  .analysis-card {
    padding: 15px;
  }
}
</style>