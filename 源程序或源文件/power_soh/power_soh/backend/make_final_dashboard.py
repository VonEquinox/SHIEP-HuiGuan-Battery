import os

vue_code = r"""<template>
  <div class="big-screen-container">
    
    <div class="screen-header">
      <div class="header-left"></div>
      <div class="header-center">
        <h2>多园区储能柜健康监测与减碳管理平台</h2>
      </div>
      <div class="header-right">
        <el-radio-group v-model="currentView" size="small" class="view-switch">
          <el-radio-button value="global">全局总览大屏</el-radio-button>
          <el-radio-button value="cabinet">单柜详情大屏</el-radio-button>
        </el-radio-group>
        <div class="time-display">{{ currentTime }}</div>
      </div>
    </div>

    <div v-if="currentView === 'global'" class="screen-body">
      <div class="top-cards">
        <div class="kpi-card">
          <div class="kpi-title">总装机容量</div>
          <div class="kpi-value text-blue">150.5 <span class="unit">MWh</span></div>
          <div class="kpi-trend positive"><span class="trend-icon">↑</span><span>2.5% 较上月</span></div>
          <div class="kpi-info"><span class="info-item">接入园区: 6个</span><span class="info-item">储能柜: 148台</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">储能柜在线率</div>
          <div class="kpi-value text-green">98.6 <span class="unit">%</span></div>
          <div class="kpi-trend positive"><span class="trend-icon">↑</span><span>0.3% 较上周</span></div>
          <div class="kpi-info"><span class="info-item">在线: 146台</span><span class="info-item">离线: 2台</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">累计峰谷套利收益</div>
          <div class="kpi-value text-yellow">1,245.8 <span class="unit">万元</span></div>
          <div class="kpi-trend positive"><span class="trend-icon">↑</span><span>125.3 万元</span></div>
          <div class="kpi-info"><span class="info-item">本月: 85.2万元</span><span class="info-item">上月: 78.9万元</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">累计节约电池更换成本</div>
          <div class="kpi-value text-cyan">452.3 <span class="unit">万元</span></div>
          <div class="kpi-trend positive"><span class="trend-icon">↑</span><span>32.1 万元</span></div>
          <div class="kpi-info"><span class="info-item">避免更换: 12组</span><span class="info-item">延长寿命: 2年</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">累计碳减排量</div>
          <div class="kpi-value text-green">8,642.5 <span class="unit">吨 CO₂</span></div>
          <div class="kpi-trend positive"><span class="trend-icon">↑</span><span>1,245 吨</span></div>
          <div class="kpi-info"><span class="info-item">本月: 420吨</span><span class="info-item">目标: 10,000吨</span></div>
        </div>
      </div>

      <div class="main-layout">
        <div class="layout-left">
          <div class="chart-box" style="height: 60%;">
            <div class="box-title text-glow">多园区储能数据拓扑网 (100%离线·点击下钻)</div>
            <div ref="mapChartRef" class="chart-content map-container"></div>
          </div>
          <div class="chart-box" style="height: 40%;">
            <div class="box-title">各园区储能柜平均 SOH 排名</div>
            <div ref="sohRankChartRef" class="chart-content"></div>
          </div>
        </div>

        <div class="layout-center">
          <div class="chart-box alert-box">
            <div class="box-title">全网安全运行总览</div>
            <div class="alert-stats">
              <div class="stat-item">
                <div class="stat-icon green-icon"><el-icon><Select /></el-icon></div>
                <div class="stat-num text-green">142</div><div class="stat-label">正常运行柜</div><div class="stat-percentage">96.6%</div>
              </div>
              <div class="stat-item">
                <div class="stat-icon yellow-icon"><el-icon><Warning /></el-icon></div>
                <div class="stat-num text-yellow">5</div><div class="stat-label">预警储能柜</div><div class="stat-percentage">3.4%</div>
              </div>
              <div class="stat-item">
                <div class="stat-icon red-icon"><el-icon><CircleClose /></el-icon></div>
                <div class="stat-num text-red glow-red">1</div><div class="stat-label">紧急故障柜</div><div class="stat-percentage">0.7%</div>
              </div>
              <div class="stat-item">
                <div class="stat-icon cyan-icon"><el-icon><Document /></el-icon></div>
                <div class="stat-num text-cyan">18</div><div class="stat-label">待处理工单</div><div class="stat-percentage">12.2%</div>
              </div>
            </div>
          </div>
          <div class="chart-box">
            <div class="box-title">全网累计碳减排量趋势 (吨 CO₂)</div>
            <div ref="carbonTrendChartRef" class="chart-content"></div>
          </div>
        </div>

        <div class="layout-right">
          <div class="chart-box">
            <div class="box-title">全量电芯 SOH 健康度分布</div>
            <div ref="sohDistChartRef" class="chart-content"></div>
          </div>
          <div class="chart-box">
            <div class="box-title">各园区减碳贡献占比</div>
            <div ref="carbonPieChartRef" class="chart-content"></div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="currentView === 'cabinet'" class="screen-body">
      <div class="cabinet-info-bar">
        <div class="info-item cyber-select-wrap">
          <span>所属园区：</span>
          <el-select v-model="selectedPark" size="small" @change="onParkChange" class="cyber-select">
            <el-option v-for="p in parks" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </div>
        <div class="info-item cyber-select-wrap">
          <span>柜体编号：</span>
          <el-select v-model="selectedCabinet" size="small" @change="onCabinetChange" class="cyber-select">
            <el-option v-for="c in currentCabinets" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </div>
        <div class="info-item"><span>安装时间：</span>{{ mockCabinetInfo.installDate }}</div>
        <div class="info-item"><span>额定容量：</span>{{ mockCabinetInfo.capacity }} kWh</div>
        <div class="info-item"><span>当前循环次数：</span>{{ mockCabinetInfo.cycles }} 次</div>
        <div class="info-item"><span>整柜平均温度：</span><span class="text-yellow">{{ mockCabinetInfo.temp }} ℃</span></div>
        <div class="info-item"><span>预计剩余寿命：</span><span class="text-green">{{ mockCabinetInfo.rul }} 次</span></div>
        <div class="info-item"><span>整柜 SOH：</span><span :class="mockCabinetInfo.sohColor" style="font-size: 20px; font-weight: bold;">{{ mockCabinetInfo.soh }}%</span></div>
      </div>

      <div class="main-layout-cabinet">
        <div class="layout-left-wide">
          <div class="chart-box" style="height: 100%;">
            <div class="box-title">电芯数字孪生健康矩阵 (点击查看详情)</div>
            <div class="matrix-legend">
              <span class="legend-item"><span class="block green"></span> 正常 (SOH ≥ 85%)</span>
              <span class="legend-item"><span class="block yellow"></span> 轻度衰减 (80%~85%)</span>
              <span class="legend-item"><span class="block red"></span> 严重异常 (SOH < 80%)</span>
              <span class="legend-item total-cells">总电芯数: {{ cellMatrix.length }} 个</span>
              <span class="legend-item abnormal-cells">异常电芯: {{ abnormalCells.length }} 个</span>
            </div>
            <div class="cell-matrix">
              <div 
                v-for="cell in cellMatrix" 
                :key="cell.id" 
                :class="['cell-block', getCellClass(cell.soh)]"
                @click="handleCellClick(cell)"
                :title="`电芯 ${cell.id} - SOH: ${cell.soh}%`"
              >
                {{ cell.id }}
                <div class="cell-soh">{{ cell.soh }}%</div>
              </div>
            </div>
          </div>
        </div>

        <div class="layout-right-narrow">
          <div class="chart-box" style="height: 48%; margin-bottom: 2%;">
            <div class="box-title">最近 24 小时微观时序数据 (V/I/T)</div>
            <div ref="trend24hChartRef" class="chart-content"></div>
          </div>
          <div class="chart-box" style="height: 50%;">
            <div class="box-title text-red">本柜异常电芯智能派工清单</div>
            <div class="table-wrapper">
              <el-table :data="abnormalCells" style="width: 100%" :row-class-name="tableRowClassName" size="small">
                <el-table-column prop="id" label="电芯" width="70" />
                <el-table-column prop="soh" label="SOH" width="60" />
                <el-table-column prop="level" label="异常等级" width="80">
                  <template #default="scope">
                    <el-tag :type="scope.row.level === '二级预警' ? 'warning' : 'danger'" size="small">
                      {{ scope.row.level }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="action" label="智能派工信息">
                  <template #default="scope">
                    <div>
                      <div class="dispatch-info">
                        <span class="dispatch-label">派发给：</span>
                        <span class="dispatch-value">{{ scope.row.assigned_worker || '系统自动寻优中...' }} {{ scope.row.distance_km ? `(距 ${scope.row.distance_km}km)` : '' }}</span>
                      </div>
                      <div class="dispatch-info">
                        <span class="dispatch-label">安全提示：</span>
                        <span class="dispatch-value">{{ scope.row.safety_instructions || (scope.row.soh < 80 ? '需穿戴防电弧服' : '需穿戴绝缘手套') }}</span>
                      </div>
                      <div class="dispatch-info" style="margin-top: 5px;">
                        <el-button type="primary" size="small" @click="openOrderDetail(scope.row)">查看派工详情</el-button>
                      </div>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </div>
      </div>
    </div>

    <el-dialog
      v-model="showOrderDetail"
      title="智能运维工单详情"
      width="800px"
      destroy-on-close
    >
      <div v-if="currentOrder" class="order-detail">
        <div class="order-header">
          <div class="order-info-item"><span class="label">工单编号：</span><span class="value">WO-{{ currentOrder.id }}</span></div>
          <div class="order-info-item"><span class="label">电芯编号：</span><span class="value">{{ currentOrder.cell_id }}</span></div>
          <div class="order-info-item">
            <span class="label">告警级别：</span>
            <span class="value" :class="currentOrder.alert_level === 3 ? 'text-red' : 'text-yellow'">
              {{ currentOrder.alert_level === 3 ? '三级预警 (红级)' : '二级预警 (黄级)' }}
            </span>
          </div>
          <div class="order-info-item"><span class="label">当前状态：</span><span class="value">{{ currentOrder.status }}</span></div>
        </div>

        <div class="order-body">
          <div class="order-section">
            <h3>🤖 AI 多维智能派工决策</h3>
            <div class="order-info-item">
              <span class="label">最优匹配人员：</span>
              <span class="value text-cyan">{{ currentOrder.assigned_worker || '王建国 (高级高级工程师)' }}</span>
            </div>
            <div class="order-info-item">
              <span class="label">匹配理由：</span>
              <span class="value">当前距离最近 ({{ currentOrder.distance_km || 1.2 }} km) / 负载最低 (持单:0) / 具备高压资质</span>
            </div>
          </div>

          <div class="order-section">
            <h3>⚠️ 场景化安全作业提示 (SOP)</h3>
            <div class="safety-instructions text-yellow">
              {{ currentOrder.safety_instructions || (currentOrder.alert_level === 3 ? '【极高危】请务必佩戴防毒面具、穿戴防电弧服；作业前请先检查柜内消防七氟丙烷灭火系统是否处于待命状态；严禁单人作业，必须双人同行！' : '常规衰减：请穿戴绝缘鞋、绝缘手套；断开汇流排后进行开箱作业。') }}
            </div>
          </div>

          <div class="order-section">
            <h3>🛠️ 自动预测领料单 (BOM)</h3>
            <div class="required-parts text-green">
              {{ currentOrder.required_parts || '1. 磷酸铁锂 18650 备用电芯 x1 节； 2. 内阻测试仪 x1； 3. 绝缘胶带 x1 卷。' }}
            </div>
          </div>

          <div class="order-section">
            <h3>📍 故障路径自动规划</h3>
            <div class="map-container" ref="orderMapRef" style="height: 300px; width: 100%;"></div>
          </div>
        </div>

        <div class="order-footer" v-if="currentOrder.status === 'Pending'">
          <el-form :model="orderForm" label-width="80px">
            <el-form-item label="处置记录">
              <el-input type="textarea" v-model="orderForm.notes" rows="3" placeholder="请输入现场作业记录与更换结果..."></el-input>
            </el-form-item>
            <el-form-item>
              <el-button type="success" @click="closeOrder(currentOrder.id, orderForm.notes)">确认闭环此工单</el-button>
              <el-button @click="showOrderDetail = false">暂不处理</el-button>
            </el-form-item>
          </el-form>
        </div>
      </div>
    </el-dialog>

  </div> </template>

<script>
import { ref, onMounted, onUnmounted, nextTick, watch, computed } from 'vue'
import { Select, Warning, CircleClose, Document } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
// 务必确保您的 @/api/index.js 里有这两个方法，否则这里会报错
import { getWorkOrders, resolveWorkOrder } from '@/api'

export default {
  name: 'Dashboard',
  components: { Select, Warning, CircleClose, Document },
  setup() {
    const currentView = ref('global')
    const currentTime = ref('')
    let timer = null

    const mapChartRef = ref(null)
    const sohRankChartRef = ref(null)
    const carbonTrendChartRef = ref(null)
    const sohDistChartRef = ref(null)
    const carbonPieChartRef = ref(null)
    const trend24hChartRef = ref(null)
    let charts = {}

    const cellMatrix = ref([])
    const abnormalCells = ref([])
    
    // 工单相关数据
    const workOrders = ref([])
    const currentOrder = ref(null)
    const showOrderDetail = ref(false)
    const orderForm = ref({ notes: '' })
    const orderMapRef = ref(null)
    let orderUpdateTimer = null
    let orderMapChart = null

    const parks = ref([
      { id: 'zj', name: '张江高科核心园区' },
      { id: 'jq', name: '浦东金桥主站' },
      { id: 'jd', name: '嘉定汽车城' },
      { id: 'lg', name: '临港风光储基地' },
      { id: 'sj', name: '松江G60科创云' },
      { id: 'mh', name: '闵行紫竹园区' }
    ])

    const cabinetsMap = {
      'zj': [{ id: 'CAB-ZJ-001', name: 'ZJ-1号柜' }, { id: 'CAB-ZJ-002', name: 'ZJ-2号柜' }],
      'jq': [{ id: 'CAB-JQ-001', name: 'JQ-1号柜' }, { id: 'CAB-JQ-002', name: 'JQ-2号柜' }],
      'jd': [{ id: 'CAB-JD-001', name: 'JD-危险柜(模拟告警)' }],
      'lg': [{ id: 'CAB-LG-001', name: 'LG-1号方舱' }],
      'sj': [{ id: 'CAB-SJ-001', name: 'SJ-主备柜' }],
      'mh': [{ id: 'CAB-MH-001', name: 'MH-测试柜' }]
    }

    const selectedPark = ref('zj')
    const selectedCabinet = ref('CAB-ZJ-001')
    const currentCabinets = computed(() => cabinetsMap[selectedPark.value] || [])

    const mockCabinetInfo = ref({
      installDate: '2022-05-12', capacity: 500, cycles: 856, temp: 32.4, rul: 1420, soh: 88.5, sohColor: 'text-green'
    })

    const generateCellData = () => {
      const matrix = []
      const abnormals = []
      const seed = selectedCabinet.value.charCodeAt(selectedCabinet.value.length - 1)
      let totalSoh = 0
      
      for (let i = 1; i <= 124; i++) {
        const id = `C-${i.toString().padStart(3, '0')}`
        let soh = 0
        const rand = Math.random()
        
        if (selectedPark.value === 'jd') {
          if (rand > 0.8) soh = 70 + Math.random() * 9 
          else if (rand > 0.5) soh = 80 + Math.random() * 5 
          else soh = 85 + Math.random() * 10 
        } else {
          if (rand > 0.96) soh = 75 + Math.random() * 4.9 
          else if (rand > 0.90) soh = 80 + Math.random() * 4.9 
          else soh = 86 + Math.random() * 14 
        }
        
        const cell = { id, soh: parseFloat(soh.toFixed(1)) }
        totalSoh += cell.soh
        matrix.push(cell)

        if (soh < 85) {
          abnormals.push({
            id: cell.id, soh: cell.soh,
            rul: Math.max(0, Math.floor((cell.soh - 70) * 10)),
            level: cell.soh < 80 ? '三级预警' : '二级预警',
            action: cell.soh < 80 ? '24小时内紧急更换' : '15天内安排更换'
          })
        }
      }
      
      cellMatrix.value = matrix
      abnormalCells.value = abnormals.sort((a, b) => a.soh - b.soh)

      const avgSoh = (totalSoh / 124).toFixed(1)
      mockCabinetInfo.value.soh = avgSoh
      mockCabinetInfo.value.sohColor = avgSoh >= 85 ? 'text-green' : avgSoh >= 80 ? 'text-yellow' : 'text-red'
      mockCabinetInfo.value.cycles = 500 + seed * 100 + Math.floor(Math.random() * 50)
      mockCabinetInfo.value.rul = Math.max(0, Math.floor((avgSoh - 70) * 10))
      mockCabinetInfo.value.temp = (25 + Math.random() * 10).toFixed(1)
    }

    const fetchWorkOrders = async () => {
      try {
        const response = await getWorkOrders()
        workOrders.value = response.data
        if(workOrders.value && workOrders.value.length > 0) {
            updateAbnormalCellsWithWorkOrders()
        }
      } catch (error) {
        console.error('获取工单数据失败:', error)
      }
    }
    
    const updateAbnormalCellsWithWorkOrders = () => {
      if (abnormalCells.value.length === 0) return
      abnormalCells.value = abnormalCells.value.map(cell => {
        const order = workOrders.value.find(order => order.cell_id === cell.id)
        if (order) {
          return {
            ...cell,
            assigned_worker: order.assigned_worker || '王建国 (高级工程师)',
            distance_km: order.distance_km || '1.2',
            safety_instructions: order.safety_instructions,
            required_parts: order.required_parts,
            dbOrderId: order.id,
            dbStatus: order.status,
            dbAlertLevel: order.alert_level
          }
        }
        return cell
      })
    }

    const openOrderDetail = (cell) => {
      // 模拟组装完整的订单数据用于展示
      currentOrder.value = {
        id: cell.dbOrderId || Math.floor(Math.random() * 10000),
        cell_id: cell.id,
        alert_level: cell.soh < 80 ? 3 : 2,
        status: cell.dbStatus || 'Pending',
        assigned_worker: cell.assigned_worker || '王建国 (高级工程师)',
        distance_km: cell.distance_km || (Math.random() * 5).toFixed(1),
        safety_instructions: cell.safety_instructions,
        required_parts: cell.required_parts
      }
      showOrderDetail.value = true
    }

    const closeOrder = async (orderId, notes) => {
      try {
        // 如果是从真实数据库读的 orderId，则调用接口
        if(workOrders.value.find(o => o.id === orderId)) {
            await resolveWorkOrder(orderId, notes || '已按SOP规范完成电芯更换，测试正常。')
        }
        await fetchWorkOrders()
        showOrderDetail.value = false
        ElMessage.success("智能工单已成功闭环！")
      } catch (error) {
        console.error('闭环工单失败:', error)
      }
    }

    const onParkChange = () => {
      selectedCabinet.value = currentCabinets.value[0].id
      onCabinetChange()
    }

    const onCabinetChange = () => {
      generateCellData()
      initCabinetCharts()
      fetchWorkOrders()
    }

    const getCellClass = (soh) => {
      if (soh >= 85) return 'bg-green'
      if (soh >= 80) return 'bg-yellow'
      return 'bg-red'
    }

    const handleCellClick = (cell) => {
      if (cell.soh < 85) openOrderDetail(cell)
      else alert(`健康电芯 ${cell.id} \nSOH: ${cell.soh}%\n预测剩余寿命: 充足`)
    }

    const tableRowClassName = ({ row }) => {
      if (row.soh < 80) return 'danger-row'
      return 'warning-row'
    }

    const initTopologyChart = () => {
      if (!mapChartRef.value) return
      charts.map = echarts.init(mapChartRef.value)
      
      charts.map.setOption({
        backgroundColor: 'transparent',
        tooltip: {
          trigger: 'item',
          backgroundColor: 'rgba(0,0,0,0.9)',
          borderColor: '#00F5FF',
          textStyle: { color: '#fff' },
          formatter: function(params) {
            if (params.seriesType === 'effectScatter') {
              const statusColor = params.color || '#00F5FF'
              return `<div style="font-weight:bold;font-size:16px;margin-bottom:10px;color:${statusColor}">${params.name}</div>` + 
                     `<div style="margin-bottom:5px;"><span style="color:#8898aa">节点状态:</span> <strong style="color:${statusColor}">${params.data.value[2]}</strong></div>` +
                     `<div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(0,245,255,0.3);"><i style="color:#00FFA3;font-size:12px;">点击下钻至该园区</i></div>`
            }
            return params.name
          }
        },
        grid: { top: 40, bottom: 40, left: 40, right: 40 },
        xAxis: { min: 0, max: 100, show: false },
        yAxis: { min: 0, max: 100, show: false },
        series: [
          {
            type: 'lines',
            zlevel: 1,
            effect: { show: true, period: 2, trailLength: 0.4, color: '#00F5FF', symbolSize: 5 },
            lineStyle: {
              color: 'rgba(0, 245, 255, 0.4)', width: 2, curveness: 0.2, shadowBlur: 10, shadowColor: '#00F5FF'
            },
            data: [
              { coords: [[60, 65], [85, 45]] }, { coords: [[60, 65], [70, 15]] },
              { coords: [[35, 50], [60, 65]] }, { coords: [[35, 50], [45, 25]] }, { coords: [[20, 75], [35, 50]] }
            ]
          },
          {
            name: '园区节点',
            type: 'effectScatter',
            zlevel: 2,
            symbolSize: 25,
            showEffectOn: 'render',
            rippleEffect: { brushType: 'stroke', scale: 4, period: 1.5 },
            itemStyle: {
              color: (params) => {
                const statusColors = { '正常': '#00FFA3', '预警': '#FFD700', '故障': '#FF4D4F' }
                return statusColors[params.value[2]] || '#00F5FF'
              },
              shadowBlur: 30, shadowColor: '#fff'
            },
            label: { show: true, formatter: '{b}', position: 'right', color: '#fff', fontWeight: 'bold' },
            data: [
              { name: '张江高科核心节点', value: [60, 65, '预警'] },
              { name: '浦东金桥主站', value: [85, 45, '正常'] },
              { name: '临港风光储基地', value: [70, 15, '正常'] },
              { name: '松江G60科创云', value: [35, 50, '正常'] },
              { name: '闵行紫竹园区', value: [45, 25, '正常'] },
              { name: '嘉定汽车城', value: [20, 75, '故障'] }
            ]
          }
        ]
      })

      charts.map.on('click', (params) => {
        if (params.seriesType === 'effectScatter') {
          const nameToIdMap = { '张江高科核心节点': 'zj', '浦东金桥主站': 'jq', '嘉定汽车城': 'jd', '临港风光储基地': 'lg', '松江G60科创云': 'sj', '闵行紫竹园区': 'mh' }
          if(nameToIdMap[params.name]) {
            selectedPark.value = nameToIdMap[params.name]
            onParkChange() 
            currentView.value = 'cabinet'
          }
        }
      })
    }

    const initOrderMap = () => {
      if (!orderMapRef.value || !currentOrder.value) return
      if (orderMapChart) orderMapChart.dispose()
      orderMapChart = echarts.init(orderMapRef.value)
      
      const faultLocation = [121.474, 31.230]
      const workerLocation = [121.484, 31.225]
      
      orderMapChart.setOption({
        backgroundColor: 'rgba(16, 28, 56, 0.6)',
        tooltip: { trigger: 'item' },
        geo: {
          map: 'china', roam: true, zoom: 12, center: faultLocation,
          itemStyle: { areaColor: 'rgba(0, 102, 255, 0.2)', borderColor: 'rgba(0, 245, 255, 0.5)' }
        },
        series: [
          {
            type: 'lines', coordinateSystem: 'geo',
            data: [{ coords: [workerLocation, faultLocation], lineStyle: { color: '#00F5FF', width: 2 } }],
            effect: { show: true, period: 2, trailLength: 0.3, color: '#00F5FF', symbolSize: 5 }
          },
          {
            type: 'effectScatter', coordinateSystem: 'geo',
            data: [
              { name: '故障柜位置', value: [...faultLocation, 100], itemStyle: { color: '#FF4D4F' }, symbolSize: 15 },
              { name: '王建国 (空闲)', value: [...workerLocation, 80], itemStyle: { color: '#00FFA3' }, symbolSize: 12 }
            ]
          }
        ]
      })
    }

    const initGlobalCharts = () => {
      initTopologyChart() 

      if (sohRankChartRef.value) {
        charts.rank = echarts.init(sohRankChartRef.value)
        charts.rank.setOption({
          grid: { top: 10, right: 30, bottom: 20, left: 70 },
          xAxis: { type: 'value', splitLine: { show: false }, axisLabel: { color: '#8898aa' }, min: 75 },
          yAxis: { type: 'category', data: ['嘉定', '松江', '浦东', '临港', '闵行', '张江'], axisLabel: { color: '#fff', fontWeight: 'bold' } },
          series: [{
            type: 'bar', data: [79.1, 85.5, 86.5, 88.2, 91.0, 93.4],
            itemStyle: { color: new echarts.graphic.LinearGradient(1, 0, 0, 0, [{ offset: 0, color: '#00F5FF' }, { offset: 1, color: '#0066FF' }]), borderRadius: [0, 5, 5, 0] },
            label: { show: true, position: 'right', color: '#00F5FF', formatter: '{c}%' }
          }]
        })
      }

      if (carbonTrendChartRef.value) {
        charts.trend = echarts.init(carbonTrendChartRef.value)
        charts.trend.setOption({
          grid: { top: 30, right: 20, bottom: 20, left: 50 },
          xAxis: { type: 'category', data: ['1月', '2月', '3月', '4月', '5月', '6月'], axisLabel: { color: '#8898aa' } },
          yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }, axisLabel: { color: '#8898aa' } },
          series: [{
            data: [1200, 2500, 3800, 5400, 6900, 8642], type: 'line', smooth: true,
            areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(0, 255, 163, 0.5)' }, { offset: 1, color: 'rgba(0, 255, 163, 0.0)' }]) },
            itemStyle: { color: '#00FFA3' }
          }]
        })
      }

      if (sohDistChartRef.value) {
        charts.dist = echarts.init(sohDistChartRef.value)
        charts.dist.setOption({
          grid: { top: 20, right: 20, bottom: 20, left: 40 },
          xAxis: { type: 'category', data: ['<75%', '75-80%', '80-85%', '85-90%', '>90%'], axisLabel: { color: '#8898aa' } },
          yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }, axisLabel: { color: '#8898aa' } },
          series: [{
            type: 'bar', data: [2, 5, 18, 56, 43],
            itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#8A2BE2' }, { offset: 1, color: '#4B0082' }]), borderRadius: [4, 4, 0, 0] }
          }]
        })
      }

      if (carbonPieChartRef.value) {
        charts.pie = echarts.init(carbonPieChartRef.value)
        charts.pie.setOption({
          tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
          series: [{
            type: 'pie', radius: ['40%', '70%'], center: ['50%', '45%'],
            itemStyle: { borderRadius: 5, borderColor: '#0b0f19', borderWidth: 2 },
            label: { show: false },
            data: [
              { value: 35, name: '延寿减碳', itemStyle: { color: '#00F5FF' } },
              { value: 45, name: '光伏消纳', itemStyle: { color: '#00FFA3' } },
              { value: 20, name: '峰谷套利', itemStyle: { color: '#FFD700' } }
            ]
          }]
        })
      }
    }

    const initCabinetCharts = () => {
      if (trend24hChartRef.value) {
        charts.trend24 = echarts.init(trend24hChartRef.value)
        const times = Array.from({length: 24}, (_, i) => `${i}:00`)
        charts.trend24.setOption({
          tooltip: { trigger: 'axis' }, legend: { data: ['电压(V)', '电流(A)', '温度(℃)'], textStyle: { color: '#fff' } },
          grid: { top: 40, right: 40, bottom: 30, left: 60 },
          xAxis: { type: 'category', data: times },
          yAxis: [{ type: 'value', min: 2.0, splitLine: {show: false} }, { type: 'value', splitLine: {show: false} }],
          series: [
            { name: '电压(V)', type: 'line', data: Array.from({length: 24}, () => 3.2 + Math.random()*0.2), itemStyle: { color: '#00F5FF' } },
            { name: '电流(A)', type: 'line', data: Array.from({length: 24}, () => Math.random()*8 - 4), itemStyle: { color: '#FFD700' } },
            { name: '温度(℃)', type: 'line', yAxisIndex: 1, data: Array.from({length: 24}, () => 25 + Math.random()*10), itemStyle: { color: '#FF4D4F' } }
          ]
        })
      }
    }

    const updateTime = () => {
      currentTime.value = new Date().toLocaleString('zh-CN', { hour12: false })
    }

    const resizeCharts = () => { Object.values(charts).forEach(chart => chart && chart.resize()) }

    onMounted(() => {
      updateTime()
      timer = setInterval(updateTime, 1000)
      generateCellData()
      nextTick(() => { initGlobalCharts() })
      window.addEventListener('resize', resizeCharts)
      fetchWorkOrders()
      orderUpdateTimer = setInterval(fetchWorkOrders, 30000)
    })

    watch(currentView, (newVal) => {
      Object.values(charts).forEach(chart => chart && chart.dispose()); charts = {}
      nextTick(() => { newVal === 'global' ? initGlobalCharts() : initCabinetCharts() })
    })

    watch(showOrderDetail, (newVal) => {
      if (newVal) nextTick(() => { initOrderMap() })
      else if (orderMapChart) { orderMapChart.dispose(); orderMapChart = null }
    })

    onUnmounted(() => {
      clearInterval(timer); clearInterval(orderUpdateTimer); window.removeEventListener('resize', resizeCharts)
      Object.values(charts).forEach(chart => chart && chart.dispose()); if (orderMapChart) orderMapChart.dispose()
    })

    return {
      currentView, currentTime, mapChartRef, sohRankChartRef, carbonTrendChartRef, sohDistChartRef, carbonPieChartRef, trend24hChartRef,
      cellMatrix, abnormalCells, getCellClass, handleCellClick, tableRowClassName, parks, cabinetsMap, selectedPark, selectedCabinet, currentCabinets,
      onParkChange, onCabinetChange, mockCabinetInfo, workOrders, showOrderDetail, currentOrder, orderForm, orderMapRef, fetchWorkOrders, openOrderDetail, closeOrder
    }
  }
}
</script>

<style scoped>
.big-screen-container { background-color: #0b0f19; color: #fff; min-height: 100vh; padding: 10px 20px; font-family: Arial, sans-serif; overflow-x: hidden; }
.screen-header { display: flex; justify-content: space-between; align-items: center; height: 60px; border-bottom: 2px solid rgba(0, 245, 255, 0.5); margin-bottom: 20px; }
.header-center h2 { margin: 0; font-size: 28px; font-weight: bold; color: #00F5FF; text-shadow: 0 0 10px rgba(0, 245, 255, 0.5); }
.header-right { display: flex; align-items: center; gap: 20px; }
.time-display { font-size: 16px; color: #00F5FF; }
:deep(.el-radio-button__inner) { background: rgba(0, 102, 255, 0.2); border-color: #0066FF; color: #fff; }
:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) { background: #0066FF; box-shadow: 0 0 10px #0066FF; }

.top-cards { display: flex; justify-content: space-between; margin-bottom: 20px; }
.kpi-card { flex: 1; background: rgba(16, 28, 56, 0.8); border: 1px solid rgba(0, 245, 255, 0.3); margin: 0 10px; padding: 15px; border-radius: 8px; text-align: center; }
.kpi-title { font-size: 14px; color: #8898aa; }
.kpi-value { font-size: 32px; font-weight: bold; margin: 10px 0; }
.kpi-trend { font-size: 12px; color: #00FFA3; }
.kpi-info { margin-top: 10px; font-size: 11px; color: #8898aa; border-top: 1px solid rgba(0, 245, 255, 0.2); padding-top: 8px; }
.text-blue { color: #00F5FF; } .text-green { color: #00FFA3; } .text-yellow { color: #FFD700; } .text-cyan { color: #00FFFF; } .text-red { color: #FF4D4F; }

.main-layout { display: flex; height: calc(100vh - 200px); gap: 20px; }
.layout-left, .layout-right { flex: 3; display: flex; flex-direction: column; gap: 20px; }
.layout-center { flex: 4; display: flex; flex-direction: column; gap: 20px; }

.chart-box { flex: 1; background: rgba(16, 28, 56, 0.6); border: 1px solid rgba(0, 102, 255, 0.3); border-radius: 8px; padding: 15px; display: flex; flex-direction: column; }
.box-title { font-size: 16px; font-weight: bold; color: #fff; margin-bottom: 10px; border-left: 4px solid #00F5FF; padding-left: 10px; }
.chart-content { flex: 1; width: 100%; height: 100%; }

.alert-stats { display: flex; justify-content: space-around; align-items: center; height: 100%; }
.stat-item { text-align: center; }
.stat-icon { font-size: 24px; margin-bottom: 5px; }
.stat-num { font-size: 40px; font-weight: bold; }
.stat-label { font-size: 14px; color: #8898aa; }

.cabinet-info-bar { display: flex; flex-wrap: wrap; background: rgba(16, 28, 56, 0.8); border: 1px solid rgba(0, 245, 255, 0.3); padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; gap: 20px; align-items: center; }
.info-item { font-size: 15px; }

.main-layout-cabinet { display: flex; height: calc(100vh - 180px); gap: 20px; }
.layout-left-wide { flex: 5; }
.layout-right-narrow { flex: 4; display: flex; flex-direction: column; }

.cell-matrix { display: grid; grid-template-columns: repeat(auto-fill, minmax(50px, 1fr)); gap: 8px; overflow-y: auto; padding: 10px; max-height: 80%; }
.cell-block { height: 45px; display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 10px; font-weight: bold; border-radius: 4px; cursor: pointer; color: #000; }
.bg-green { background: #00FFA3; } .bg-yellow { background: #FFD700; } .bg-red { background: #FF4D4F; color: #fff; animation: blink 1.5s infinite; }
@keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }

.table-wrapper { height: 100%; overflow-y: auto; }
:deep(.el-table) { background-color: transparent !important; color: #fff; }
:deep(.el-table th.el-table__cell), :deep(.el-table tr) { background-color: transparent !important; }
:deep(.warning-row) { color: #FFD700; } :deep(.danger-row) { color: #FF4D4F; font-weight: bold; }

/* 派工与弹窗样式 */
.dispatch-info { font-size: 11px; margin-bottom: 4px; }
.dispatch-label { color: #8898aa; } .dispatch-value { color: #00F5FF; font-weight: bold; }

.order-detail { padding: 10px 0; }
.order-header { display: flex; gap: 20px; border-bottom: 1px solid rgba(0, 245, 255, 0.3); padding-bottom: 15px; margin-bottom: 20px; }
.order-info-item .label { color: #8898aa; } .order-info-item .value { color: #fff; font-weight: bold; }
.order-section { margin-bottom: 20px; }
.order-section h3 { color: #00F5FF; border-left: 4px solid #00F5FF; padding-left: 10px; }
.safety-instructions, .required-parts { background: rgba(16, 28, 56, 0.8); border: 1px solid rgba(0, 245, 255, 0.3); padding: 10px; border-radius: 4px; }
:deep(.el-dialog) { background: rgba(11, 15, 25, 0.95); border: 1px solid #00F5FF; box-shadow: 0 0 20px rgba(0, 245, 255, 0.3); }
:deep(.el-dialog__title) { color: #00F5FF; font-weight: bold; }
:deep(.el-dialog__body) { color: #fff; }
:deep(.el-textarea__inner) { background: rgba(16, 28, 56, 0.8); border: 1px solid #00F5FF; color: #fff; }
</style>
"""

clean_code = vue_code.replace('\xa0', ' ').replace('　', ' ')

try:
    with open("Dashboard.vue", "w", encoding="utf-8") as f:
        f.write(clean_code)
    print("✅ 完美修复版 Dashboard.vue 生成成功！")
except Exception as e:
    print(f"❌ 失败: {e}")