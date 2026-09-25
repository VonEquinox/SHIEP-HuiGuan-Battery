<template>
  <div class="data-management">
    <el-card class="card-container">
      <template #header>
        <div class="card-header">
          <span>电芯特征数据管理</span>
          <div class="header-actions">
            <el-button type="primary" @click="exportData">
              <el-icon><Download /></el-icon>
              导出特征数据
            </el-button>
          </div>
        </div>
      </template>

      <!-- 统计卡片 -->
      <el-row :gutter="20">
        <el-col :span="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-content">
              <el-icon :size="32" color="#409EFF"><Coin /></el-icon>
              <div class="stat-info">
                <div class="stat-value">{{ totalBatteries }}</div>
                <div class="stat-label">电芯总数</div>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-content">
              <el-icon :size="32" color="#67C23A"><DataAnalysis /></el-icon>
              <div class="stat-info">
                <div class="stat-value">{{ totalRecords.toLocaleString() }}+</div>
                <div class="stat-label">总循环记录</div>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-content">
              <el-icon :size="32" color="#E6A23C"><TrendCharts /></el-icon>
              <div class="stat-info">
                <div class="stat-value">6</div>
                <div class="stat-label">高级特征维度</div>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-content">
              <el-icon :size="32" color="#F56C6C"><CircleCheck /></el-icon>
              <div class="stat-info">
                <div class="stat-value">{{ dataCompleteness }}%</div>
                <div class="stat-label">数据完整性</div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 筛选卡片 -->
      <el-card shadow="hover" style="margin-top: 20px">
        <template #header>
          <span>特征数据查询与筛选</span>
        </template>
        <el-form :inline="true" :model="filterForm" class="filter-form">
          <el-form-item label="电芯编号 (Cell ID)">
            <el-select
              v-model="filterForm.cellId"
              placeholder="选择电芯"
              clearable
              filterable
              style="width: 200px"
              @change="handleBatteryChange"
            >
              <el-option v-for="id in cellIds" :key="id" :label="`电芯 #${id}`" :value="id" />
            </el-select>
          </el-form-item>

          <el-form-item label="循环次数范围">
            <el-slider
              v-model="filterForm.cycleRange"
              range
              :min="0"
              :max="maxCycle"
              :step="10"
              style="width: 300px"
            />
            <span class="range-text">{{ filterForm.cycleRange[0] }} - {{ filterForm.cycleRange[1] }}</span>
          </el-form-item>

          <el-form-item>
            <el-button type="primary" @click="queryData">
              <el-icon><Search /></el-icon>查询
            </el-button>
            <el-button @click="resetFilter">
              <el-icon><Refresh /></el-icon>重置
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 选项卡 -->
      <el-tabs v-model="activeTab" type="border-card" style="margin-top: 20px" @tab-click="handleTabClick">
        <!-- 原始数据表 -->
        <el-tab-pane label="高级特征数据流" name="rawData">
          <el-card shadow="hover">
            <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center">
                <span>电芯全生命周期特征数据 (对齐模型输入)</span>
                <el-button size="small" @click="downloadTableData">
                  <el-icon><Download /></el-icon>下载当前数据
                </el-button>
              </div>
            </template>
            <el-table
              :data="tableData"
              stripe
              border
              height="500"
              :default-sort="{ prop: 'cycleIndex', order: 'ascending' }"
            >
              <el-table-column prop="cellId" label="电芯编号" width="120" fixed></el-table-column>
              <el-table-column prop="cycleIndex" label="循环序号" width="100" sortable></el-table-column>
              <el-table-column prop="deltaQMean" label="容量差值均值(ΔQ)" width="150">
                <template #default="scope">{{ scope.row.deltaQMean.toFixed(4) }}</template>
              </el-table-column>
              <el-table-column prop="deltaQVar" label="容量差值方差" width="120">
                <template #default="scope">{{ scope.row.deltaQVar.toFixed(4) }}</template>
              </el-table-column>
              <el-table-column prop="cycleCapacity" label="放电容量(Ah)" width="120">
                <template #default="scope">{{ scope.row.cycleCapacity.toFixed(4) }}</template>
              </el-table-column>
              <el-table-column prop="dcirOhm" label="直流内阻(DCIR)" width="130">
                <template #default="scope">{{ scope.row.dcirOhm.toFixed(4) }}</template>
              </el-table-column>
              <el-table-column prop="vPlateauLen" label="放电平台长度" width="120">
                <template #default="scope">{{ scope.row.vPlateauLen.toFixed(4) }}</template>
              </el-table-column>
              <el-table-column prop="chargeEfficiency" label="充电效率" width="100">
                <template #default="scope">{{ scope.row.chargeEfficiency.toFixed(4) }}</template>
              </el-table-column>
              <el-table-column prop="soh" label="SOH(%)" width="100">
                <template #default="scope">{{ scope.row.soh.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column prop="rul" label="RUL" width="100" sortable>
                <template #default="scope">
                  <el-tag :type="getRulTagType(scope.row.rul)">{{ scope.row.rul }}</el-tag>
                </template>
              </el-table-column>
            </el-table>

            <!-- 分页：使用传统 :current-page + @update:current-page 避免 IDE 警告 -->
            <el-pagination
              :current-page="pagination.currentPage"
              :page-size="pagination.pageSize"
              :page-sizes="[50, 100, 200, 500]"
              :total="pagination.total"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="handleSizeChange"
              @current-change="handleCurrentChange"
              style="margin-top: 20px; justify-content: center"
            />
          </el-card>
        </el-tab-pane>

        <!-- 统计分析 -->
        <el-tab-pane label="统计分析" name="statistics">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-card shadow="hover">
                <template #header><span>特征数据统计指标</span></template>
                <el-table :data="statisticsData" stripe border height="400">
                  <el-table-column prop="feature" label="特征" width="140" fixed></el-table-column>
                  <el-table-column prop="mean" label="均值" width="100">
                    <template #default="scope">{{ scope.row.mean.toFixed(4) }}</template>
                  </el-table-column>
                  <el-table-column prop="variance" label="方差" width="100">
                    <template #default="scope">{{ scope.row.variance.toFixed(4) }}</template>
                  </el-table-column>
                  <el-table-column prop="min" label="最小值" width="100">
                    <template #default="scope">{{ scope.row.min.toFixed(4) }}</template>
                  </el-table-column>
                  <el-table-column prop="max" label="最大值" width="100">
                    <template #default="scope">{{ scope.row.max.toFixed(4) }}</template>
                  </el-table-column>
                </el-table>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card shadow="hover">
                <template #header><span>特征分布情况</span></template>
                <div ref="distributionChartRef" style="height: 400px"></div>
              </el-card>
            </el-col>
          </el-row>
        </el-tab-pane>

        <!-- 趋势分析 -->
        <el-tab-pane label="趋势分析" name="trend">
          <el-card shadow="hover">
            <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center">
                <span>电芯特征参数变化趋势</span>
                <el-select
                  v-model="selectedFeatures"
                  multiple
                  placeholder="选择特征"
                  style="width: 400px"
                  @change="updateTrendChart"
                >
                  <el-option v-for="feature in allFeatures" :key="feature" :label="feature" :value="feature" />
                </el-select>
              </div>
            </template>
            <div ref="trendChartRef" style="height: 450px"></div>
          </el-card>

          <el-row :gutter="20" style="margin-top: 20px">
            <el-col :span="12">
              <el-card shadow="hover">
                <template #header><span>RUL与关键特征散点图</span></template>
                <div ref="rulScatterChartRef" style="height: 400px"></div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card shadow="hover">
                <template #header><span>容量衰减分布</span></template>
                <div ref="pclHistogramChartRef" style="height: 400px"></div>
              </el-card>
            </el-col>
          </el-row>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { Download, Search, Refresh, DataAnalysis, Coin, TrendCharts, CircleCheck } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
// 如果后端接口已就绪，可导入 request
// import request from '@/utils/request'

// ---------- 类型定义 ----------
interface BatteryData {
  cellId: string
  cycleIndex: number
  deltaQMean: number
  deltaQVar: number
  cycleCapacity: number
  dcirOhm: number
  vPlateauLen: number
  chargeEfficiency: number
  soh: number
  rul: number
  pcl?: number
}

interface StatisticsItem {
  feature: string
  mean: number
  variance: number
  min: number
  max: number
}

interface FilterForm {
  cellId: string
  cycleRange: [number, number]
}

interface Pagination {
  currentPage: number
  pageSize: number
  total: number
}

// ---------- 响应式数据 ----------
const cellIds = ref<string[]>(['CELL-001', 'CELL-002', 'CELL-003'])
const totalBatteries = ref<number>(124)
const totalRecords = ref<number>(0)
const dataCompleteness = ref<number>(99.8)

const filterForm = reactive<FilterForm>({
  cellId: 'CELL-001',
  cycleRange: [0, 1000]
})

const maxCycle = ref<number>(1000)
const activeTab = ref<string>('rawData')

const allFeatures = ref<string[]>([
  '容量差值均值(ΔQ)',
  '容量差值方差',
  '放电容量(Ah)',
  '直流内阻(DCIR)',
  '放电平台长度',
  '充电效率',
  'SOH(%)'
])
const selectedFeatures = ref<string[]>(['放电容量(Ah)', '直流内阻(DCIR)', 'SOH(%)'])

const statisticsData = ref<StatisticsItem[]>([])
const tableData = ref<BatteryData[]>([])
const pagination = reactive<Pagination>({
  currentPage: 1,
  pageSize: 50,
  total: 0
})

// ECharts 实例和 DOM 引用
const distributionChartRef = ref<HTMLElement | null>(null)
const trendChartRef = ref<HTMLElement | null>(null)
const rulScatterChartRef = ref<HTMLElement | null>(null)
const pclHistogramChartRef = ref<HTMLElement | null>(null)

let distributionChart: echarts.ECharts | null = null
let trendChart: echarts.ECharts | null = null
let rulScatterChart: echarts.ECharts | null = null
let pclHistogramChart: echarts.ECharts | null = null

// ---------- 辅助函数 ----------
const formatNumber = (value: any): string => {
  if (value === null || value === undefined || value === '') return ''
  const num = parseFloat(value)
  if (isNaN(num)) return ''
  return parseFloat(num.toFixed(6)).toString()
}

// 模拟加载表格数据（实际可替换为 request 调用）
const loadTableData = async (): Promise<void> => {
  try {
    // 模拟数据生成
    const mockData: BatteryData[] = []
    const start = (pagination.currentPage - 1) * pagination.pageSize
    for (let i = 0; i < pagination.pageSize; i++) {
      const cycle = start + i + 1
      mockData.push({
        cellId: filterForm.cellId,
        cycleIndex: cycle,
        deltaQMean: -0.03 + Math.random() * 0.01,
        deltaQVar: 0.0001 + Math.random() * 0.00005,
        cycleCapacity: 1.0 - cycle * 0.0002 + Math.random() * 0.02,
        dcirOhm: 0.018 + cycle * 0.00001 + Math.random() * 0.002,
        vPlateauLen: 3.5 + Math.random() * 0.3,
        chargeEfficiency: 0.96 - cycle * 0.00002 + Math.random() * 0.01,
        soh: 100 - cycle * 0.08 + Math.random() * 2,
        rul: 1000 - cycle,
        pcl: Math.random() * 20
      })
    }
    tableData.value = mockData
    pagination.total = 1200 // 模拟总记录数
    totalRecords.value = pagination.total
  } catch (error) {
    ElMessage.error('加载特征数据失败')
  }
}

// 模拟加载统计数据
const loadBatteryStatistics = async (): Promise<void> => {
  statisticsData.value = [
    { feature: '容量差值均值(ΔQ)', mean: -0.03, variance: 0.0001, min: -0.05, max: -0.01 },
    { feature: '直流内阻(DCIR)', mean: 0.018, variance: 0.00002, min: 0.015, max: 0.025 },
    { feature: '放电容量(Ah)', mean: 0.95, variance: 0.01, min: 0.8, max: 1.1 },
    { feature: '充电效率', mean: 0.96, variance: 0.001, min: 0.9, max: 0.99 }
  ]
}

// 查询
const queryData = async (): Promise<void> => {
  await loadTableData()
  await loadBatteryStatistics()
  ElMessage.success('查询成功')
}

// 重置筛选
const resetFilter = (): void => {
  filterForm.cellId = 'CELL-001'
  filterForm.cycleRange = [0, 1000]
  queryData()
}

// 电芯切换
const handleBatteryChange = (): void => {
  queryData()
}

// 分页事件
const handleSizeChange = (size: number): void => {
  pagination.pageSize = size
  pagination.currentPage = 1
  loadTableData()
}

const handleCurrentChange = (page: number): void => {
  pagination.currentPage = page
  loadTableData()
}

// RUL 标签类型
const getRulTagType = (rul: number): 'success' | 'warning' | 'danger' => {
  if (rul > 500) return 'success'
  if (rul > 200) return 'warning'
  return 'danger'
}

// 导出
const exportData = (): void => {
  ElMessage.info('功能开发中：将对接全量特征库下载...')
}

// 下载当前表格数据为 CSV
const downloadTableData = (): void => {
  if (!tableData.value || tableData.value.length === 0) {
    ElMessage.warning('当前表格没有数据')
    return
  }

  const csvHeaders = ['Cell_ID', 'Cycle_Index', 'DeltaQ_Mean', 'DeltaQ_Var', 'Cycle_Capacity_Ah', 'DCIR_Ohm', 'V_Plateau_Len', 'Charge_Efficiency', 'SOH', 'RUL']
  let csv = '\uFEFF' + csvHeaders.join(',') + '\n'
  tableData.value.forEach(row => {
    const values = [
      row.cellId,
      row.cycleIndex,
      formatNumber(row.deltaQMean),
      formatNumber(row.deltaQVar),
      formatNumber(row.cycleCapacity),
      formatNumber(row.dcirOhm),
      formatNumber(row.vPlateauLen),
      formatNumber(row.chargeEfficiency),
      formatNumber(row.soh),
      row.rul
    ]
    csv += values.join(',') + '\n'
  })

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  link.setAttribute('href', url)
  link.setAttribute('download', `电芯特征_${filterForm.cellId}_${new Date().toISOString().split('T')[0]}.csv`)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  ElMessage.success(`成功下载 ${tableData.value.length} 条数据`)
}

// ---------- 图表初始化 ----------
const initDistributionChart = (): void => {
  if (!distributionChartRef.value) return
  if (distributionChart) distributionChart.dispose()
  distributionChart = echarts.init(distributionChartRef.value)
  distributionChart.setOption({
    tooltip: { trigger: 'item' },
    grid: { left: '15%', right: '10%', bottom: '15%' },
    xAxis: {
      type: 'category',
      data: ['ΔQ均值', '直流内阻', '放电容量', '平台长度', '充电效率', 'SOH'],
      axisLabel: { rotate: 45 }
    },
    yAxis: { type: 'value', name: '归一化值' },
    series: [
      {
        type: 'boxplot',
        data: [
          [0.2, 0.4, 0.5, 0.6, 0.8],
          [0.1, 0.3, 0.4, 0.7, 0.9],
          [0.3, 0.5, 0.6, 0.8, 0.9],
          [0.2, 0.3, 0.5, 0.6, 0.8],
          [0.5, 0.7, 0.8, 0.9, 0.99],
          [0.6, 0.7, 0.8, 0.9, 1.0]
        ],
        itemStyle: { color: '#409EFF' }
      }
    ]
  })
}

const updateTrendChart = (): void => {
  if (!trendChartRef.value) return
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value)
  }

  const cycles: number[] = []
  for (let i = 0; i <= 1000; i += 10) cycles.push(i)

  const series = selectedFeatures.value.map(feature => {
    const baseValue = Math.random() * 50 + 50
    const data = cycles.map(cycle => Number((baseValue - (cycle / 1000) * 30 + (Math.random() - 0.5) * 5).toFixed(2)))
    return { name: feature, type: 'line', smooth: true, data }
  })

  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: selectedFeatures.value, top: '8%' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: cycles, name: '循环次数' },
    yAxis: { type: 'value', name: '相对数值' },
    series
  })
}

const initRulScatterChart = (): void => {
  if (!rulScatterChartRef.value) return
  if (rulScatterChart) rulScatterChart.dispose()
  rulScatterChart = echarts.init(rulScatterChartRef.value)
  const data: [number, number][] = []
  for (let i = 0; i < 300; i++) {
    data.push([60 + Math.random() * 40, Math.random() * 2000])
  }
  rulScatterChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => `SOH: ${p.value[0].toFixed(2)}%<br/>RUL: ${p.value[1].toFixed(0)}`
    },
    grid: { left: '10%', right: '10%', bottom: '10%', top: '15%' },
    xAxis: { name: 'SOH(%)', nameLocation: 'center', nameGap: 30 },
    yAxis: { name: 'RUL', nameLocation: 'center', nameGap: 40 },
    series: [
      {
        type: 'scatter',
        symbolSize: 6,
        data,
        itemStyle: { color: '#5470c6', opacity: 0.6 }
      }
    ]
  })
}

const initPclHistogramChart = (): void => {
  if (!pclHistogramChartRef.value) return
  if (pclHistogramChart) pclHistogramChart.dispose()
  pclHistogramChart = echarts.init(pclHistogramChartRef.value)
  pclHistogramChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: '8%', right: '4%', bottom: '15%', top: '15%' },
    xAxis: {
      type: 'category',
      data: ['0-5', '5-10', '10-15', '15-20', '20-25'],
      name: '容量衰减 PCL(%)'
    },
    yAxis: { type: 'value', name: '电芯数量' },
    series: [
      {
        type: 'bar',
        data: [80, 200, 150, 60, 20],
        itemStyle: { color: '#67C23A' }
      }
    ]
  })
}

// 选项卡点击时延迟渲染图表（确保 DOM 已渲染）
const handleTabClick = (tab: any): void => {
  nextTick(() => {
    setTimeout(() => {
      if (tab.paneName === 'statistics') {
        initDistributionChart()
      } else if (tab.paneName === 'trend') {
        updateTrendChart()
        initRulScatterChart()
        initPclHistogramChart()
      }
      // 触发窗口 resize 让图表自适应
      window.dispatchEvent(new Event('resize'))
    }, 100)
  })
}

// 窗口大小变化自适应
const resizeHandler = (): void => {
  distributionChart?.resize()
  trendChart?.resize()
  rulScatterChart?.resize()
  pclHistogramChart?.resize()
}

// 监听选中的特征变化，自动更新趋势图（如果当前在趋势标签页）
watch(selectedFeatures, () => {
  if (activeTab.value === 'trend') {
    updateTrendChart()
  }
})

// ---------- 生命周期 ----------
onMounted(async () => {
  await loadTableData()
  await loadBatteryStatistics()
  window.addEventListener('resize', resizeHandler)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeHandler)
  distributionChart?.dispose()
  trendChart?.dispose()
  rulScatterChart?.dispose()
  pclHistogramChart?.dispose()
})
</script>

<style scoped>
.data-management {
  padding: 20px;
  font-size: 14px;
  width: 100%;
}

.card-container {
  min-height: 800px;
  font-size: 14px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.stat-card {
  cursor: pointer;
  transition: all 0.3s;
}

.stat-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.stat-content {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 10px;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 5px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}

.range-text {
  margin-left: 10px;
  color: #606266;
  font-size: 14px;
}

:deep(.el-table) {
  font-size: 14px;
}

:deep(.el-card) {
  font-size: 14px;
}

:deep(.el-card__header) {
  font-size: 16px;
  font-weight: 600;
}
</style>