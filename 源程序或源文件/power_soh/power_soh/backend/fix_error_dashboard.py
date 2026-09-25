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
        <div class="kpi-card"><div class="kpi-title">总装机容量</div><div class="kpi-value text-blue">150.5 <span class="unit">MWh</span></div></div>
        <div class="kpi-card"><div class="kpi-title">储能柜在线率</div><div class="kpi-value text-green">98.6 <span class="unit">%</span></div></div>
        <div class="kpi-card"><div class="kpi-title">累计峰谷套利收益</div><div class="kpi-value text-yellow">1,245.8 <span class="unit">万元</span></div></div>
        <div class="kpi-card"><div class="kpi-title">累计节约电池更换成本</div><div class="kpi-value text-cyan">452.3 <span class="unit">万元</span></div></div>
        <div class="kpi-card"><div class="kpi-title">累计碳减排量</div><div class="kpi-value text-green">8,642.5 <span class="unit">吨 CO₂</span></div></div>
      </div>

      <div class="main-layout">
        <div class="layout-left">
          <div class="chart-box" style="height: 60%;">
            <div class="box-title text-glow">上海市储能节点实时监控 (离线地图)</div>
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
              <div class="stat-item"><div class="stat-icon green-icon"><el-icon><Select /></el-icon></div><div class="stat-num text-green">142</div><div class="stat-label">正常运行柜</div></div>
              <div class="stat-item"><div class="stat-icon yellow-icon"><el-icon><Warning /></el-icon></div><div class="stat-num text-yellow">5</div><div class="stat-label">预警储能柜</div></div>
              <div class="stat-item"><div class="stat-icon red-icon"><el-icon><CircleClose /></el-icon></div><div class="stat-num text-red glow-red">1</div><div class="stat-label">紧急故障柜</div></div>
              <div class="stat-item"><div class="stat-icon cyan-icon"><el-icon><Document /></el-icon></div><div class="stat-num text-cyan">18</div><div class="stat-label">待处理工单</div></div>
            </div>
          </div>
          <div class="chart-box">
            <div class="box-title">全网累计碳减排量趋势 (吨 CO₂)</div>
            <div ref="carbonTrendChartRef" class="chart-content"></div>
          </div>
        </div>

        <div class="layout-right">
          <div class="chart-box"><div class="box-title">全量电芯 SOH 健康度分布</div><div ref="sohDistChartRef" class="chart-content"></div></div>
          <div class="chart-box"><div class="box-title">各园区减碳贡献占比</div><div ref="carbonPieChartRef" class="chart-content"></div></div>
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
        <div class="info-item"><span>整柜 SOH：</span><span :class="mockCabinetInfo.sohColor" style="font-size: 20px; font-weight: bold;">{{ mockCabinetInfo.soh }}%</span></div>
      </div>

      <div class="main-layout-cabinet">
        <div class="layout-left-wide">
          <div class="chart-box" style="height: 100%;">
            <div class="box-title">电芯数字孪生健康矩阵 (点击查看详情)</div>
            <div class="cell-matrix">
              <div v-for="cell in cellMatrix" :key="cell.id" :class="['cell-block', getCellClass(cell.soh)]" @click="handleCellClick(cell)">
                {{ cell.id }}<div class="cell-soh">{{ cell.soh }}%</div>
              </div>
            </div>
          </div>
        </div>

        <div class="layout-right-narrow">
          <div class="chart-box" style="height: 48%; margin-bottom: 2%;"><div class="box-title">24 小时微观时序</div><div ref="trend24hChartRef" class="chart-content"></div></div>
          <div class="chart-box" style="height: 50%;">
            <div class="box-title text-red">异常电芯智能派工</div>
            <div class="table-wrapper">
              <el-table :data="abnormalCells" style="width: 100%" :row-class-name="tableRowClassName" size="small">
                <el-table-column prop="id" label="编号" width="70" />
                <el-table-column prop="soh" label="SOH" width="60" />
                <el-table-column prop="level" label="等级" width="80">
                  <template #default="scope"><el-tag :type="scope.row.level === '二级预警' ? 'warning' : 'danger'" size="small">{{ scope.row.level }}</el-tag></template>
                </el-table-column>
                <el-table-column prop="action" label="派工信息">
                  <template #default="scope">
                    <el-button type="primary" size="small" @click="openOrderDetail(scope.row)">查看派工单</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="showOrderDetail" title="智能运维工单详情" width="800px" destroy-on-close>
      <div v-if="currentOrder" class="order-detail">
        <div class="order-header">
          <div class="order-info-item"><span class="label">工单编号：</span><span class="value">WO-{{ currentOrder.id }}</span></div>
          <div class="order-info-item"><span class="label">电芯编号：</span><span class="value">{{ currentOrder.cell_id }}</span></div>
        </div>
        <div class="order-body">
          <div class="order-section"><h3>🤖 AI 智能派工</h3><div class="value text-cyan">{{ currentOrder.assigned_worker || '王建国' }}</div></div>
        </div>
        <div class="order-footer" v-if="currentOrder.status === 'Pending'">
          <el-button type="success" @click="closeOrder(currentOrder.id, '已修复')">闭环工单</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, nextTick, watch, computed } from 'vue'
import * as echarts from 'echarts'
import { getWorkOrders, resolveWorkOrder } from '@/api'

// 【修复点 1：补齐所有 Element Plus 的图标组件导入】
import { Select, Warning, CircleClose, Document } from '@element-plus/icons-vue'

export default {
  name: 'Dashboard',
  // 【修复点 2：向 Vue 注册这些图标组件，否则模板不认识它们】
  components: {
    Select, Warning, CircleClose, Document
  },
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
    const workOrders = ref([])
    const currentOrder = ref(null)
    const showOrderDetail = ref(false)

    const parks = ref([
      { id: 'zj', name: '张江高科核心园区' }, { id: 'jq', name: '浦东金桥主站' },
      { id: 'jd', name: '嘉定汽车城' }, { id: 'lg', name: '临港风光储基地' },
      { id: 'sj', name: '松江G60科创云' }, { id: 'mh', name: '闵行紫竹园区' }
    ])

    const cabinetsMap = {
      'zj': [{ id: 'CAB-ZJ-001', name: 'ZJ-1号柜' }], 'jq': [{ id: 'CAB-JQ-001', name: 'JQ-1号柜' }],
      'jd': [{ id: 'CAB-JD-001', name: 'JD-危险柜(告警)' }], 'lg': [{ id: 'CAB-LG-001', name: 'LG-1号方舱' }],
      'sj': [{ id: 'CAB-SJ-001', name: 'SJ-主备柜' }], 'mh': [{ id: 'CAB-MH-001', name: 'MH-测试柜' }]
    }

    const selectedPark = ref('zj')
    const selectedCabinet = ref('CAB-ZJ-001')
    const currentCabinets = computed(() => cabinetsMap[selectedPark.value] || [])
    const mockCabinetInfo = ref({ installDate: '2022-05-12', capacity: 500, cycles: 856, temp: 32.4, rul: 1420, soh: 88.5, sohColor: 'text-green' })

    const generateCellData = () => {
      const matrix = [], abnormals = []
      let totalSoh = 0
      for (let i = 1; i <= 124; i++) {
        const id = `C-${i.toString().padStart(3, '0')}`
        let soh = selectedPark.value === 'jd' ? 70 + Math.random()*20 : 80 + Math.random()*15
        soh = parseFloat(soh.toFixed(1))
        totalSoh += soh
        matrix.push({ id, soh })
        if (soh < 85) abnormals.push({ id, soh, rul: Math.max(0, Math.floor((soh - 70)*10)), level: soh < 80 ? '三级预警' : '二级预警' })
      }
      cellMatrix.value = matrix
      abnormalCells.value = abnormals.sort((a, b) => a.soh - b.soh)
      mockCabinetInfo.value.soh = (totalSoh / 124).toFixed(1)
      mockCabinetInfo.value.sohColor = mockCabinetInfo.value.soh >= 85 ? 'text-green' : 'text-red'
    }

    const onParkChange = () => { selectedCabinet.value = currentCabinets.value[0].id; onCabinetChange() }
    const onCabinetChange = () => { generateCellData(); initCabinetCharts() }
    const getCellClass = (soh) => soh >= 85 ? 'bg-green' : soh >= 80 ? 'bg-yellow' : 'bg-red'
    const tableRowClassName = ({ row }) => row.soh < 80 ? 'danger-row' : 'warning-row'

    const fetchWorkOrders = async () => {
      try { const res = await getWorkOrders(); workOrders.value = res.data; } catch (e) {}
    }
    const openOrderDetail = (cell) => { currentOrder.value = { id: Math.floor(Math.random() * 10000), cell_id: cell.id, alert_level: cell.soh < 80 ? 3 : 2, status: 'Pending' }; showOrderDetail.value = true; }
    const closeOrder = async (id, notes) => { showOrderDetail.value = false; }
    const handleCellClick = (cell) => { if (cell.soh < 85) openOrderDetail(cell) }

    const initRealMapChart = () => {
      if (!mapChartRef.value) return
      charts.map = echarts.init(mapChartRef.value)
      
      // 读取存在本地 public 文件夹下的 shanghai.json 
      fetch('/shanghai.json')
        .then(res => res.json())
        .then(geoJson => {
          echarts.registerMap('shanghai', geoJson)
          
          charts.map.setOption({
            backgroundColor: 'transparent',
            tooltip: { 
              trigger: 'item', backgroundColor: 'rgba(0,0,0,0.8)', borderColor: '#00F5FF', textStyle: { color: '#fff' },
              formatter: '{b}<br/>状态: {c}<br/><i style="color:#00FFA3;font-size:12px;">(点击下钻)</i>' 
            },
            geo: {
              map: 'shanghai',
              roam: true, zoom: 1.1,
              label: { show: true, color: 'rgba(255,255,255,0.6)', fontSize: 10 },
              itemStyle: {
                areaColor: 'rgba(0, 102, 255, 0.15)', borderColor: '#00F5FF', borderWidth: 1.5,
                shadowColor: 'rgba(0, 245, 255, 0.5)', shadowBlur: 15
              },
              emphasis: { itemStyle: { areaColor: 'rgba(0, 102, 255, 0.5)' }, label: {color: '#fff'} }
            },
            series: [
              {
                name: '储能节点',
                type: 'effectScatter', 
                coordinateSystem: 'geo',
                symbolSize: 20,
                showEffectOn: 'render',
                rippleEffect: { brushType: 'stroke', scale: 4, period: 3 },
                itemStyle: {
                  color: (params) => {
                    const statusColors = { '正常': '#00FFA3', '预警': '#FFD700', '故障': '#FF4D4F' }
                    return statusColors[params.value[2]] || '#00F5FF'
                  },
                  shadowBlur: 20, shadowColor: '#fff'
                },
                label: { show: true, formatter: '{b}', position: 'right', color: '#fff', fontWeight: 'bold' },
                data: [
                  { name: '浦东金桥主站', value: [121.614379, 31.251517, '正常'] },
                  { name: '闵行紫竹园区', value: [121.451629, 31.022459, '正常'] },
                  { name: '嘉定汽车城', value: [121.26554, 31.334768, '故障'] },
                  { name: '临港风光储基地', value: [121.933333, 30.883333, '正常'] },
                  { name: '张江高科核心节点', value: [121.605389, 31.20364, '预警'] },
                  { name: '松江G60科创云', value: [121.2287, 31.0322, '正常'] }
                ]
              }
            ]
          })

          charts.map.on('click', (params) => {
            if (params.seriesType === 'effectScatter') {
              const nameToIdMap = { '张江高科核心节点': 'zj', '浦东金桥主站': 'jq', '嘉定汽车城': 'jd', '临港风光储基地': 'lg', '松江G60科创云': 'sj', '闵行紫竹园区': 'mh' }
              if(nameToIdMap[params.name]) {
                selectedPark.value = nameToIdMap[params.name]
                onParkChange(); currentView.value = 'cabinet'
              }
            }
          })
        })
        .catch(err => {
          console.error('获取本地地图文件失败，请检查 public/shanghai.json 是否存在！', err)
        })
    }

    const initGlobalCharts = () => {
      initRealMapChart() 

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
          grid: { top: 30, right: 20, bottom: 20, left: 50 }, xAxis: { type: 'category', data: ['1月', '2月', '3月', '4月', '5月', '6月'], axisLabel: { color: '#8898aa' } },
          yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }, axisLabel: { color: '#8898aa' } },
          series: [{ data: [1200, 2500, 3800, 5400, 6900, 8642], type: 'line', smooth: true, itemStyle: { color: '#00FFA3' } }]
        })
      }
      if (sohDistChartRef.value) {
        charts.dist = echarts.init(sohDistChartRef.value)
        charts.dist.setOption({
          grid: { top: 20, right: 20, bottom: 20, left: 40 }, xAxis: { type: 'category', data: ['<75%', '75-80%', '80-85%', '85-90%', '>90%'], axisLabel: { color: '#8898aa' } },
          yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }, axisLabel: { color: '#8898aa' } },
          series: [{ type: 'bar', data: [2, 5, 18, 56, 43], itemStyle: { color: '#8A2BE2', borderRadius: [4, 4, 0, 0] } }]
        })
      }
      if (carbonPieChartRef.value) {
        charts.pie = echarts.init(carbonPieChartRef.value)
        charts.pie.setOption({
          tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.8)' },
          series: [{ type: 'pie', radius: ['40%', '70%'], center: ['50%', '45%'], data: [{ value: 35, name: '延寿减碳', itemStyle: { color: '#00F5FF' } }, { value: 45, name: '光伏消纳', itemStyle: { color: '#00FFA3' } }, { value: 20, name: '峰谷套利', itemStyle: { color: '#FFD700' } }] }]
        })
      }
    }

    const initCabinetCharts = () => {
      if (trend24hChartRef.value) {
        charts.trend24 = echarts.init(trend24hChartRef.value)
        const times = Array.from({length: 24}, (_, i) => `${i}:00`)
        charts.trend24.setOption({
          tooltip: { trigger: 'axis' }, grid: { top: 40, right: 40, bottom: 30, left: 60 },
          xAxis: { type: 'category', data: times }, yAxis: [{ type: 'value', min: 2.0, splitLine: {show: false} }, { type: 'value', splitLine: {show: false} }],
          series: [
            { name: '电压(V)', type: 'line', data: Array.from({length: 24}, () => 3.2 + Math.random()*0.2), itemStyle: { color: '#00F5FF' } },
            { name: '电流(A)', type: 'line', data: Array.from({length: 24}, () => Math.random()*8 - 4), itemStyle: { color: '#FFD700' } },
            { name: '温度(℃)', type: 'line', yAxisIndex: 1, data: Array.from({length: 24}, () => 25 + Math.random()*10), itemStyle: { color: '#FF4D4F' } }
          ]
        })
      }
    }

    const updateTime = () => { currentTime.value = new Date().toLocaleString('zh-CN', { hour12: false }) }
    const resizeCharts = () => { Object.values(charts).forEach(chart => chart && chart.resize()) }

    onMounted(() => {
      updateTime(); timer = setInterval(updateTime, 1000); generateCellData()
      nextTick(() => { initGlobalCharts() }); window.addEventListener('resize', resizeCharts)
    })

    watch(currentView, (newVal) => {
      Object.values(charts).forEach(chart => chart && chart.dispose()); charts = {}
      nextTick(() => { newVal === 'global' ? initGlobalCharts() : initCabinetCharts() })
    })

    onUnmounted(() => { clearInterval(timer); window.removeEventListener('resize', resizeCharts); Object.values(charts).forEach(chart => chart && chart.dispose()) })

    return {
      currentView, currentTime, mapChartRef, sohRankChartRef, carbonTrendChartRef, sohDistChartRef, carbonPieChartRef, trend24hChartRef,
      cellMatrix, abnormalCells, getCellClass, handleCellClick, tableRowClassName, parks, cabinetsMap, selectedPark, selectedCabinet, currentCabinets,
      onParkChange, onCabinetChange, mockCabinetInfo, currentOrder, showOrderDetail, openOrderDetail, closeOrder
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
.main-layout-cabinet { display: flex; height: calc(100vh - 180px); gap: 20px; }
.layout-left-wide { flex: 5; } .layout-right-narrow { flex: 4; display: flex; flex-direction: column; }

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
with open("Dashboard.vue", "w", encoding="utf-8") as f:
    f.write(clean_code)
print("✅ 完美修复版 Dashboard.vue 生成成功！")