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
        </div>
        <div class="kpi-card">
          <div class="kpi-title">储能柜在线率</div>
          <div class="kpi-value text-green">98.6 <span class="unit">%</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">累计峰谷套利收益</div>
          <div class="kpi-value text-yellow">1,245.8 <span class="unit">万元</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">累计节约电池更换成本</div>
          <div class="kpi-value text-cyan">452.3 <span class="unit">万元</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">累计碳减排量</div>
          <div class="kpi-value text-green">8,642.5 <span class="unit">吨 CO₂</span></div>
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
              <div class="stat-item"><div class="stat-num text-green">142</div><div class="stat-label">正常运行柜</div></div>
              <div class="stat-item"><div class="stat-num text-yellow">5</div><div class="stat-label">预警储能柜</div></div>
              <div class="stat-item"><div class="stat-num text-red glow-red">1</div><div class="stat-label">紧急故障柜</div></div>
              <div class="stat-item"><div class="stat-num text-cyan">18</div><div class="stat-label">待处理工单</div></div>
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
            </div>
            <div class="cell-matrix">
              <div 
                v-for="cell in cellMatrix" 
                :key="cell.id" 
                :class="['cell-block', getCellClass(cell.soh)]"
                @click="handleCellClick(cell)"
              >
                {{ cell.id }}
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
            <div class="box-title text-red">本柜异常电芯告警清单</div>
            <div class="table-wrapper">
              <el-table :data="abnormalCells" style="width: 100%" :row-class-name="tableRowClassName" size="small">
                <el-table-column prop="id" label="电芯编号" width="90" />
                <el-table-column prop="soh" label="SOH(%)" width="70" />
                <el-table-column prop="rul" label="剩余寿命" width="80" />
                <el-table-column prop="level" label="异常等级" width="80">
                  <template #default="scope">
                    <el-tag :type="scope.row.level === '二级预警' ? 'warning' : 'danger'" size="small">
                      {{ scope.row.level }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="action" label="建议处置" />
              </el-table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, nextTick, watch, computed } from 'vue'
import * as echarts from 'echarts'

export default {
  name: 'Dashboard',
  setup() {
    const currentView = ref('global')
    const currentTime = ref('')
    let timer = null

    // 图表引用
    const mapChartRef = ref(null)
    const sohRankChartRef = ref(null)
    const carbonTrendChartRef = ref(null)
    const sohDistChartRef = ref(null)
    const carbonPieChartRef = ref(null)
    const trend24hChartRef = ref(null)
    let charts = {}

    // 【修复点】：显式定义电芯矩阵的响应式变量，防止 ReferenceError
    const cellMatrix = ref([])
    const abnormalCells = ref([])

    // ================== 下拉框数据源 ==================
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
      'jq': [{ id: 'CAB-JQ-001', name: 'JQ-1号柜' }, { id: 'CAB-JQ-002', name: 'JQ-2号柜' }, { id: 'CAB-JQ-003', name: 'JQ-3号柜' }],
      'jd': [{ id: 'CAB-JD-001', name: 'JD-危险柜(告警)' }],
      'lg': [{ id: 'CAB-LG-001', name: 'LG-1号储能方舱' }, { id: 'CAB-LG-002', name: 'LG-2号储能方舱' }],
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

    const onParkChange = () => {
      selectedCabinet.value = currentCabinets.value[0].id
      onCabinetChange()
    }

    const onCabinetChange = () => {
      generateCellData()
      initCabinetCharts()
    }

    const getCellClass = (soh) => {
      if (soh >= 85) return 'bg-green'
      if (soh >= 80) return 'bg-yellow'
      return 'bg-red'
    }

    const handleCellClick = (cell) => {
      alert(`电芯 ${cell.id} 详情：\nSOH: ${cell.soh}%\n预测剩余循环寿命: ${Math.max(0, Math.floor((cell.soh - 70) * 10))} 次\n状态: ${cell.soh < 80 ? '严重异常' : cell.soh < 85 ? '轻度衰减' : '健康'}`)
    }

    const tableRowClassName = ({ row }) => {
      if (row.soh < 80) return 'danger-row'
      return 'warning-row'
    }

    // ================= 核心：纯离线动态流光拓扑网 =================
    const initTopologyChart = () => {
      if (!mapChartRef.value) return
      charts.map = echarts.init(mapChartRef.value)
      
      charts.map.setOption({
        backgroundColor: 'transparent',
        tooltip: {
          trigger: 'item',
          backgroundColor: 'rgba(0,0,0,0.8)',
          borderColor: '#00F5FF',
          textStyle: { color: '#fff' },
          formatter: function(params) {
            if (params.seriesType === 'effectScatter') {
              return `<div style="font-weight:bold;font-size:14px;margin-bottom:5px;">${params.name}</div>` + 
                     `节点状态: <strong style="color:${params.color}">${params.data.value[2]}</strong><br/>` +
                     `<i style="color:#00FFA3;font-size:12px;margin-top:5px;display:block;">( 点击可下钻至该园区 )</i>`
            }
            return params.name
          }
        },
        grid: { top: 30, bottom: 30, left: 30, right: 30 },
        xAxis: { min: 0, max: 100, show: false },
        yAxis: { min: 0, max: 100, show: false },
        series: [
          {
            type: 'lines',
            zlevel: 1,
            effect: {
              show: true,
              period: 3,
              trailLength: 0.4,
              color: '#00F5FF',
              symbolSize: 4
            },
            lineStyle: {
              color: 'rgba(0, 245, 255, 0.2)',
              width: 1.5,
              curveness: 0.2
            },
            data: [
              { name: '数据流', coords: [[60, 65], [85, 45]] },
              { name: '数据流', coords: [[60, 65], [70, 15]] },
              { name: '数据流', coords: [[35, 50], [60, 65]] },
              { name: '数据流', coords: [[35, 50], [45, 25]] },
              { name: '数据流', coords: [[20, 75], [35, 50]] }
            ]
          },
          {
            name: '园区节点',
            type: 'effectScatter',
            zlevel: 2,
            symbolSize: 22,
            showEffectOn: 'render',
            rippleEffect: { brushType: 'stroke', scale: 4, period: 2.5 },
            itemStyle: {
              color: (params) => {
                const statusColors = { '正常': '#00FFA3', '预警': '#FFD700', '故障': '#FF4D4F' }
                return statusColors[params.value[2]] || '#00F5FF'
              },
              shadowBlur: 20, shadowColor: '#fff'
            },
            label: { 
              show: true, formatter: '{b}', position: 'right', color: '#fff',
              fontSize: 14, fontWeight: 'bold', textShadowColor: '#000', textShadowBlur: 5, offset: [10, 0]
            },
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

      // 下钻点击事件
      charts.map.on('click', (params) => {
        if (params.seriesType === 'effectScatter') {
          const nameToIdMap = {
            '张江高科核心节点': 'zj',
            '浦东金桥主站': 'jq',
            '嘉定汽车城': 'jd',
            '临港风光储基地': 'lg',
            '松江G60科创云': 'sj',
            '闵行紫竹园区': 'mh'
          }
          const targetParkId = nameToIdMap[params.name]
          if(targetParkId) {
            selectedPark.value = targetParkId
            onParkChange() 
            currentView.value = 'cabinet'
          }
        }
      })
    }

    const initGlobalCharts = () => {
      initTopologyChart() 

      if (sohRankChartRef.value) {
        charts.rank = echarts.init(sohRankChartRef.value)
        charts.rank.setOption({
          grid: { top: 10, right: 30, bottom: 20, left: 70 },
          xAxis: { type: 'value', splitLine: { show: false }, axisLabel: { color: '#8898aa' } },
          yAxis: { type: 'category', data: ['嘉定', '松江', '浦东', '临港', '闵行', '张江'], axisLabel: { color: '#fff', fontWeight: 'bold' } },
          series: [{
            type: 'bar',
            data: [79.1, 85.5, 86.5, 88.2, 91.0, 93.4],
            itemStyle: {
              color: new echarts.graphic.LinearGradient(1, 0, 0, 0, [
                { offset: 0, color: '#00F5FF' }, { offset: 1, color: '#0066FF' }
              ]),
              borderRadius: [0, 5, 5, 0]
            },
            label: { show: true, position: 'right', color: '#00F5FF', formatter: '{c}%', fontWeight: 'bold' }
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
            data: [1200, 2500, 3800, 5400, 6900, 8642],
            type: 'line', smooth: true,
            areaStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: 'rgba(0, 255, 163, 0.5)' }, { offset: 1, color: 'rgba(0, 255, 163, 0.0)' }
              ])
            },
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
            itemStyle: { 
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: '#8A2BE2' }, { offset: 1, color: '#4B0082' }
              ]), 
              borderRadius: [4, 4, 0, 0] 
            }
          }]
        })
      }

      if (carbonPieChartRef.value) {
        charts.pie = echarts.init(carbonPieChartRef.value)
        charts.pie.setOption({
          tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
          legend: { bottom: '5%', textStyle: { color: '#fff' } },
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
        const offset = selectedCabinet.value.charCodeAt(selectedCabinet.value.length - 1) % 5
        
        charts.trend24.setOption({
          tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
          legend: { data: ['电压(V)', '电流(A)', '温度(℃)'], textStyle: { color: '#fff' } },
          grid: { top: 40, right: 40, bottom: 20, left: 40 },
          xAxis: { type: 'category', data: times, axisLabel: { color: '#8898aa' } },
          yAxis: [
            { type: 'value', name: 'V/A', axisLabel: { color: '#8898aa' }, splitLine: { show: false }, min: 2.0 },
            { type: 'value', name: '℃', axisLabel: { color: '#8898aa' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } } }
          ],
          series: [
            { name: '电压(V)', type: 'line', data: Array.from({length: 24}, () => 3.0 + Math.random()*0.4 + offset*0.02), itemStyle: { color: '#00F5FF' } },
            { name: '电流(A)', type: 'line', data: Array.from({length: 24}, () => Math.random()*8 - 4), itemStyle: { color: '#FFD700' } },
            { name: '温度(℃)', type: 'line', yAxisIndex: 1, data: Array.from({length: 24}, () => 20 + Math.random()*15 + offset), itemStyle: { color: '#FF4D4F' } }
          ]
        })
      }
    }

    const updateTime = () => {
      const now = new Date()
      currentTime.value = now.toLocaleString('zh-CN', { hour12: false })
    }

    const resizeCharts = () => {
      Object.values(charts).forEach(chart => chart && chart.resize())
    }

    onMounted(() => {
      updateTime()
      timer = setInterval(updateTime, 1000)
      generateCellData()
      nextTick(() => { initGlobalCharts() })
      window.addEventListener('resize', resizeCharts)
    })

    watch(currentView, (newVal) => {
      Object.values(charts).forEach(chart => chart && chart.dispose())
      charts = {}
      nextTick(() => {
        if (newVal === 'global') initGlobalCharts()
        else initCabinetCharts()
      })
    })

    onUnmounted(() => {
      clearInterval(timer)
      window.removeEventListener('resize', resizeCharts)
      Object.values(charts).forEach(chart => chart && chart.dispose())
    })

    return {
      currentView, currentTime, mapChartRef, sohRankChartRef, carbonTrendChartRef,
      sohDistChartRef, carbonPieChartRef, trend24hChartRef,
      cellMatrix, abnormalCells, getCellClass, handleCellClick, tableRowClassName,
      parks, cabinetsMap, selectedPark, selectedCabinet, currentCabinets,
      onParkChange, onCabinetChange, mockCabinetInfo
    }
  }
}
</script>

<style scoped>
/* =========== 核心科技暗黑主题 =========== */
.big-screen-container {
  background-color: #0b0f19;
  color: #fff;
  min-height: 100vh;
  padding: 10px 20px;
  font-family: 'Helvetica Neue', Arial, sans-serif;
  overflow-x: hidden;
}

/* 头部样式 */
.screen-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 60px;
  background: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg"><line x1="0" y1="60" x2="100%" y2="60" stroke="%2300F5FF" stroke-width="2"/></svg>') no-repeat bottom;
  margin-bottom: 20px;
}
.header-center h2 {
  margin: 0;
  font-size: 28px;
  font-weight: bold;
  letter-spacing: 2px;
  background: linear-gradient(to right, #00F5FF, #0066FF);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  text-shadow: 0 0 10px rgba(0, 245, 255, 0.3);
}
.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}
.time-display {
  font-size: 16px;
  color: #00F5FF;
  font-family: monospace;
  text-shadow: 0 0 8px rgba(0,245,255,0.8);
}
:deep(.el-radio-button__inner) {
  background: rgba(0, 102, 255, 0.2);
  border-color: #0066FF;
  color: #fff;
}
:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: #0066FF;
  box-shadow: 0 0 10px #0066FF;
}

/* KPI 卡片 */
.top-cards {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;
}
.kpi-card {
  flex: 1;
  background: rgba(16, 28, 56, 0.8);
  border: 1px solid rgba(0, 245, 255, 0.3);
  margin: 0 10px;
  padding: 15px;
  border-radius: 8px;
  text-align: center;
  box-shadow: inset 0 0 20px rgba(0, 102, 255, 0.2);
  transition: all 0.3s;
}
.kpi-card:hover {
  transform: translateY(-3px);
  box-shadow: inset 0 0 30px rgba(0, 245, 255, 0.4);
  border: 1px solid rgba(0, 245, 255, 0.8);
}
.kpi-title { font-size: 14px; color: #8898aa; margin-bottom: 10px; }
.kpi-value { font-size: 32px; font-weight: bold; font-family: 'Impact', sans-serif; }
.unit { font-size: 14px; font-weight: normal; }

/* 文字颜色 */
.text-blue { color: #00F5FF; text-shadow: 0 0 10px rgba(0,245,255,0.8); }
.text-green { color: #00FFA3; text-shadow: 0 0 10px rgba(0,255,163,0.8); }
.text-yellow { color: #FFD700; text-shadow: 0 0 10px rgba(255,215,0,0.8); }
.text-cyan { color: #00FFFF; }
.text-red { color: #FF4D4F; text-shadow: 0 0 10px rgba(255,77,79,0.8); }
.text-glow { text-shadow: 0 0 10px rgba(255, 255, 255, 0.5); }
.glow-red { animation: textBlink 1.5s infinite; }

@keyframes textBlink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }

/* 布局 */
.main-layout { display: flex; height: calc(100vh - 200px); gap: 20px; }
.layout-left { flex: 3; display: flex; flex-direction: column; gap: 20px; }
.layout-right { flex: 3; display: flex; flex-direction: column; gap: 20px; }
.layout-center { flex: 4; display: flex; flex-direction: column; gap: 20px; }

.chart-box {
  flex: 1;
  background: rgba(16, 28, 56, 0.6);
  border: 1px solid rgba(0, 102, 255, 0.3);
  border-radius: 8px;
  padding: 15px;
  display: flex;
  flex-direction: column;
  position: relative;
}
.chart-box::before {
  content: ''; position: absolute; top: 0; left: 0; width: 15px; height: 15px; border-top: 3px solid #00F5FF; border-left: 3px solid #00F5FF;
}
.chart-box::after {
  content: ''; position: absolute; bottom: 0; right: 0; width: 15px; height: 15px; border-bottom: 3px solid #00F5FF; border-right: 3px solid #00F5FF;
}
.box-title {
  font-size: 16px; font-weight: bold; color: #fff; margin-bottom: 10px; padding-left: 10px; border-left: 4px solid #00F5FF;
}
.chart-content { flex: 1; width: 100%; height: 100%; }
.map-container { position: relative; z-index: 10; cursor: pointer; }

/* 报警统计区 */
.alert-stats { display: flex; justify-content: space-around; align-items: center; height: 100%; }
.stat-item { text-align: center; }
.stat-num { font-size: 40px; font-weight: bold; font-family: 'Impact'; }
.stat-label { font-size: 14px; color: #8898aa; margin-top: 10px; }

/* ================= 柜体详情页特有样式 ================= */
.cabinet-info-bar {
  display: flex; flex-wrap: wrap; background: rgba(16, 28, 56, 0.8); border: 1px solid rgba(0, 245, 255, 0.3);
  padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; gap: 20px; align-items: center;
}
.info-item { font-size: 15px; display: flex; align-items: center; }
.info-item > span:first-child { color: #8898aa; margin-right: 5px; }

/* 赛博风下拉框深度修改 */
.cyber-select-wrap { margin-right: 15px; }
:deep(.cyber-select .el-input__wrapper) {
  background-color: rgba(0, 102, 255, 0.1) !important;
  box-shadow: 0 0 0 1px rgba(0, 245, 255, 0.5) inset !important;
}
:deep(.cyber-select .el-input__inner) {
  color: #00F5FF !important;
  font-weight: bold;
}
:deep(.cyber-select .el-select__caret) { color: #00F5FF !important; }

.main-layout-cabinet { display: flex; height: calc(100vh - 180px); gap: 20px; }
.layout-left-wide { flex: 5; }
.layout-right-narrow { flex: 4; display: flex; flex-direction: column; }

/* 微观电芯矩阵 */
.matrix-legend { margin-bottom: 15px; display: flex; gap: 15px; font-size: 12px; }
.legend-item { display: flex; align-items: center; gap: 5px; }
.block { width: 12px; height: 12px; border-radius: 2px; }
.block.green { background: #00FFA3; box-shadow: 0 0 5px #00FFA3; }
.block.yellow { background: #FFD700; box-shadow: 0 0 5px #FFD700; }
.block.red { background: #FF4D4F; box-shadow: 0 0 5px #FF4D4F; }

.cell-matrix {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(40px, 1fr));
  gap: 8px;
  overflow-y: auto;
  padding: 10px;
}
.cell-block {
  height: 25px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: #000;
  font-weight: bold;
  border-radius: 3px;
  cursor: pointer;
  transition: transform 0.2s;
}
.cell-block:hover { transform: scale(1.2); z-index: 10; border: 1px solid #fff; }
.bg-green { background: #00FFA3; box-shadow: 0 0 6px #00FFA3; }
.bg-yellow { background: #FFD700; box-shadow: 0 0 6px #FFD700; }
.bg-red { background: #FF4D4F; box-shadow: 0 0 10px #FF4D4F; color: #fff; animation: blink 1.5s infinite; }

@keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }

/* 表格透明样式 */
.table-wrapper { height: 100%; overflow-y: auto; }
:deep(.el-table) { background-color: transparent !important; color: #fff; border: none; }
:deep(.el-table th.el-table__cell), :deep(.el-table tr) { background-color: transparent !important; }
:deep(.el-table td.el-table__cell) { border-bottom: 1px solid rgba(0, 245, 255, 0.1); }
:deep(.el-table--enable-row-hover .el-table__body tr:hover > td.el-table__cell) { background-color: rgba(0, 102, 255, 0.3) !important; }
:deep(.warning-row) { color: #FFD700; }
:deep(.danger-row) { color: #FF4D4F; font-weight: bold; }
</style>
"""

clean_code = vue_code.replace('\xa0', ' ').replace('　', ' ')

try:
    with open("Dashboard.vue", "w", encoding="utf-8") as f:
        f.write(clean_code)
    print("✅ 完美修复版 Dashboard.vue 生成成功！")
except Exception as e:
    print(f"❌ 失败: {e}")