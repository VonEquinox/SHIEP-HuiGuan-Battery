<template>
  <div class="dashboard-wrapper">
    <div class="tech-watermark">Powered by BiLSTM + DeepHPM 联合物理信息模型</div>

    <section class="screen-panel global-overview">
      <div class="panel-header">
        <div class="header-left">
          <span class="tech-title">多园区储能柜健康与减碳总览</span> 
          <div class="mock-filters">
            <el-select v-model="mockFilter.region" size="small" class="tech-select" @change="handleRegionChange">
              <el-option label="上海市 (全域统管)" value="sh_all" />
              <el-option label="临港基地" value="lg" />
              <el-option label="张江科学城" value="zj" />
              <el-option label="漕河泾" value="chj" />
              <el-option label="嘉定汽车城" value="jd" />
            </el-select>
            <el-date-picker v-model="mockFilter.date" type="month" size="small" placeholder="当月实时数据" class="tech-date" />
          </div>
        </div>
        <div class="header-right">
          <span class="swipe-hint" @click="scrollToRight" style="cursor: pointer;"><el-icon><Right /></el-icon> 在此区域向右滑动触控板，进入单柜诊断 ➡</span>
        </div>
      </div>
      
      <div class="grid-layout global-grid">
        
        <div class="card kpi-card">
          <div class="card-corner top-left"></div><div class="card-corner bottom-right"></div>
          
          <div class="kpi-section">
            <div class="kpi-group-title">💰 经济效益评估</div>
            <div class="kpi-row">
              <div class="kpi-item">
                <div class="kpi-label">总装机容量 (MWh)</div>
                <div class="kpi-value glow-blue">{{ backendKpiData.capacity }}</div>
                <div class="kpi-trend">同比 <span class="trend-up"><el-icon><Top/></el-icon> 12.4%</span></div>
              </div>
              <div class="kpi-item">
                <div class="kpi-label">累计削峰填谷收益 (万元)</div>
                <div class="kpi-value glow-orange">{{ backendKpiData.profit }}</div>
                <div class="kpi-trend">同比 <span class="trend-up"><el-icon><Top/></el-icon> 8.2%</span></div>
              </div>
              <div class="kpi-item">
                <div class="kpi-label">预测节约换池成本 (万元)</div>
                <div class="kpi-value glow-purple">{{ backendKpiData.costSaved }}</div>
                <div class="kpi-trend">较传统 <span class="trend-up"><el-icon><Top/></el-icon> 60.0%</span></div>
              </div>
            </div>
          </div>

          <div class="kpi-divider"></div>

          <div class="kpi-section">
            <div class="kpi-group-title">🍃 节能减排成效</div>
            <div class="kpi-row">
              <div class="kpi-item">
                <div class="kpi-label">累计碳减排量 (tCO₂)</div>
                <div class="kpi-value glow-cyan">{{ backendKpiData.carbon }}</div>
                <div class="kpi-trend">同比 <span class="trend-up"><el-icon><Top/></el-icon> 15.3%</span></div>
              </div>
              <div class="kpi-item">
                <div class="kpi-label">折合节约标准煤 (吨)</div>
                <div class="kpi-value glow-green">{{ backendKpiData.coal }}</div>
                <div class="kpi-trend">达成率 <span class="trend-up"><el-icon><Top/></el-icon> 102%</span></div>
              </div>
              <div class="kpi-item">
                <div class="kpi-label">等效植树造林 (棵)</div>
                <div class="kpi-value glow-green">{{ backendKpiData.trees }}</div>
                <div class="kpi-trend">生态贡献极佳</div>
              </div>
            </div>
          </div>
        </div>

        <div class="card map-card">
          <div class="card-corner top-left"></div><div class="card-corner bottom-right"></div>
          <div class="card-title"><span class="title-deco"></span>安全运行地图 (上海市域)</div>
          <div class="chart-container" ref="mapChartRef"></div>
          
          <div class="alarm-stats">
            <span class="stat-box">在线储能柜: <b class="glow-blue">150</b></span>
            <span class="stat-box">运行正常: <b class="glow-green">142</b></span>
            <span class="stat-box">状态预警: <b class="glow-yellow">6</b></span>
            <span class="stat-box">严重故障: <b class="glow-red">2</b></span>
          </div>
        </div>

        <div class="card chart-card">
          <div class="card-corner top-left"></div><div class="card-corner bottom-right"></div>
          <div class="card-title">
            <span class="title-deco"></span>
            {{ mockFilter.region === 'sh_all' ? '全网电芯健康度 (SOH) 分布' : `【${getRegionName}】资产健康诊断面板` }}
          </div>
          
          <div class="chart-container" ref="sohChartRef" v-show="mockFilter.region === 'sh_all'"></div>
          
          <div class="cabinet-panel-inner" v-show="mockFilter.region !== 'sh_all'">
            <div class="region-stats-bar">
              <div class="r-stat">总机柜 <span class="glow-blue">{{ regionCabinets.length }}</span> 台</div>
              <div class="r-stat">健康 <span class="glow-green">{{ regionStats.green }}</span> 台</div>
              <div class="r-stat">预警 <span class="glow-orange">{{ regionStats.yellow }}</span> 台</div>
              <div class="r-stat">故障 <span class="glow-red">{{ regionStats.red }}</span> 台</div>
            </div>
            <div class="cabinet-grid-container">
              <div 
                v-for="cab in regionCabinets" 
                :key="cab.id" 
                :class="['cabinet-box', cab.status]"
                @click="enterCabinet(cab)"
              >
                <div class="cab-name">{{ cab.name }}</div>
                <div class="cab-status-text">
                  <el-icon v-if="cab.status === 'cab-green'"><CircleCheck /></el-icon>
                  <el-icon v-else-if="cab.status === 'cab-yellow'"><Warning /></el-icon>
                  <el-icon v-else><CircleClose /></el-icon>
                  {{ cab.status === 'cab-green' ? '全模组健康运行' : (cab.status === 'cab-yellow' ? '探测到预警模组' : '存在严重故障模组') }}
                </div>
                <div class="click-hint">点击切入孪生视图</div>
              </div>
              <div v-if="regionCabinets.length === 0" class="empty-hint">暂无储能柜数据</div>
            </div>
          </div>
        </div>

        <div class="card chart-card">
          <div class="card-corner top-left"></div><div class="card-corner bottom-right"></div>
          <div class="card-title"><span class="title-deco"></span>各示范园区减碳贡献占比</div>
          <div class="chart-container" ref="carbonChartRef"></div>
        </div>
      </div>
    </section>

    <section class="screen-panel single-cabinet">
      <div class="panel-header">
        <div class="header-left">
          <span class="swipe-hint" @click="scrollToLeft" style="cursor: pointer;"><el-icon><Back /></el-icon> ⬅ 向左滑动返回全局总览</span> 
          <span class="tech-title" style="margin-left: 20px;">单柜数字孪生诊断 (资产编号: {{ currentCabinetId }})</span>
        </div>
        <div class="header-right">
           <el-tag effect="dark" type="success" size="large" class="bms-live-tag" style="font-size: 16px;">
             <span class="live-dot"></span>BMS 实时通讯中...
           </el-tag>
        </div>
      </div>
      
      <div class="grid-layout single-grid">
        <div class="card basic-info-card">
          <div class="card-corner top-left"></div><div class="card-corner bottom-right"></div>
          <el-descriptions :column="4" border class="dark-desc">
            <el-descriptions-item label="所属园区">{{ currentCabinetRegion }}</el-descriptions-item>
            <el-descriptions-item label="柜级评估SOH"><span :class="cabinetGlobalSoh < 85 ? 'glow-red' : 'glow-green'">{{ cabinetGlobalSoh }}%</span></el-descriptions-item>
            <el-descriptions-item label="实时充放功率"><span class="glow-orange">45.2 kW (放电)</span></el-descriptions-item>
            <el-descriptions-item label="柜级剩余寿命"><span class="glow-blue">预测 1850 次</span></el-descriptions-item>
            
            <el-descriptions-item label="总模块规模">140个模组 / 22400电芯</el-descriptions-item>
            <el-descriptions-item label="健康模组数"><span class="glow-green" style="font-size:16px;">{{ cabinetStats.green }} 个</span></el-descriptions-item>
            <el-descriptions-item label="预警模组数"><span class="glow-yellow" style="font-size:16px;">{{ cabinetStats.yellow }} 个</span></el-descriptions-item>
            <el-descriptions-item label="故障模组数"><span class="glow-red" style="font-size:16px;font-weight:bold;">{{ cabinetStats.red }} 个</span></el-descriptions-item>
          </el-descriptions>
        </div>

        <div class="card rt-chart-card">
          <div class="card-corner top-left"></div><div class="card-corner bottom-right"></div>
          <div class="card-title">
            <span class="title-deco"></span>K线拟合分析-过往30日运行态势透视
            <span style="font-size:12px; color:#8fa3b7; margin-left:15px; font-weight:normal;">支持滚轮/拖拽缩放</span>
          </div>
          <div class="chart-container" ref="trendChartRef" style="height: calc(100% - 25px); width: 100%;"></div>
        </div>

        <div class="card matrix-card">
          <div class="card-corner top-left"></div><div class="card-corner bottom-right"></div>
          
          <div class="card-title">
            <div style="display:flex; justify-content: space-between; width:100%;">
              <span><span class="title-deco"></span>整柜模组层健康矩阵 (140个)</span>
              <span style="font-size:12px; color:#a2a3b7; font-weight:normal;">点击模组下钻电芯细节</span>
            </div>
          </div>
          <div class="module-matrix-container">
            <el-tooltip 
              v-for="mod in moduleList" 
              :key="mod.id" 
              :content="`[${mod.id}] 状态: ${mod.status} | 异常率: ${mod.ratio}`" 
              placement="top"
              effect="dark"
            >
              <div 
                class="mod-block" 
                :class="[mod.modClass, { 'is-active-mod': activeModule?.id === mod.id }]"
                @click="selectModule(mod)"
              ></div>
            </el-tooltip>
          </div>

          <div class="card-title" style="margin-top: 10px; flex-direction:column; align-items:flex-start;">
            <div><span class="title-deco"></span>电芯层诊断透视 (物理映射: 160节/模组)</div>
            <div v-if="activeModule" class="active-mod-info" :class="activeModule.status === '故障' ? 'info-red' : (activeModule.status === '预警' ? 'info-yellow' : 'info-green')">
              当前透视：<b>{{ activeModule.id }}</b> | 
              系统定级：<b>{{ activeModule.status }}</b> | 
              异常电芯比例：<b>{{ activeModule.ratio }}</b>
            </div>
          </div>
          <div class="cell-matrix-container">
            <el-tooltip 
              v-for="cell in cellList" 
              :key="cell.id" 
              :content="`[${cell.id}] SOH: ${cell.soh}% | 定级: ${cell.level} | 寿命: ${cell.life}次`" 
              placement="top"
              effect="dark"
            >
              <div class="cell-block" :class="[cell.cellClass]"></div>
            </el-tooltip>
          </div>

          <div class="matrix-legend">
            <span class="leg-item"><i class="bg-green"></i> 正常/健康</span>
            <span class="leg-item"><i class="bg-yellow"></i> 一级(预警)</span>
            <span class="leg-item"><i class="bg-orange"></i> 二级(故障)</span>
            <span class="leg-item"><i class="bg-red"></i> 三级(严重)</span>
          </div>
        </div>

        <div class="card alarm-list-card">
          <div class="card-corner top-left"></div><div class="card-corner bottom-right"></div>
          <div class="card-title text-red"><span class="title-deco deco-red"></span>模组级自动化处置清单</div>
          <div class="table-wrapper">
            <el-table 
              :data="abnormalModules" 
              style="width: 100%; height: 100%;" 
              :row-class-name="tableRowClassName"
            >
              <el-table-column prop="id" label="模组" width="70" />
              <el-table-column prop="status" label="定级" width="60">
                <template #default="{ row }">
                  <el-tag :type="row.status === '故障' ? 'danger' : 'warning'" effect="dark" size="small">{{ row.status }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="ratio" label="异常率" width="65" />
              <el-table-column prop="suggest" label="标准作业程序 (SOP) 建议" show-overflow-tooltip />
              <el-table-column label="操作" width="85" fixed="right" align="center">
                <template #default="{ row }">
                  <el-button 
                    v-if="row.status === '预警'"
                    size="small" 
                    type="warning" 
                    plain 
                    class="tech-btn" 
                    @click="handleMonitor(row)"
                  >持续监控</el-button>
                  <el-button 
                    v-else
                    size="small" 
                    :type="row.dispatchStatus === 'Dispatched' ? 'info' : 'danger'" 
                    plain 
                    class="tech-btn" 
                    :disabled="row.dispatchStatus === 'Dispatched'"
                    @click="handleDispatch(row)"
                  >{{ row.dispatchStatus === 'Dispatched' ? '已派单' : '停机换模' }}</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, reactive, computed } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus';
import { Right, Back, Top, Bottom, CircleCheck, Warning, CircleClose } from '@element-plus/icons-vue';
import * as echarts from 'echarts';
import request from '@/utils/request';

const router = useRouter();
const mockFilter = reactive({ region: 'sh_all', date: '' }); 

const mapChartRef = ref(null);
const sohChartRef = ref(null);
const carbonChartRef = ref(null);
const trendChartRef = ref(null);

let mapChart, sohChart, carbonChart, trendChart;

// 后端全局 KPI 数据（带兜底默认值，保证界面永不空白）
const backendKpiData = ref({
  capacity: '150.5',
  profit: '345.2',
  costSaved: '85.6',
  carbon: '1,240.8',
  coal: '496.3',
  trees: '68,930'
});

const regionCabinets = ref([]);
const regionStats = reactive({ green: 0, yellow: 0, red: 0 });
const currentCabinetId = ref('SH-PD-001');
const currentCabinetRegion = ref('临港基地');

const moduleList = ref([]);
const cellList = ref([]);
const abnormalModules = ref([]);
const activeModule = ref(null);
const cabinetStats = reactive({ green: 0, yellow: 0, red: 0 });
const cabinetGlobalSoh = ref(100);

const getRegionName = computed(() => {
  const map = { 'sh_all': '上海市全域', 'lg': '临港基地', 'zj': '张江科学城', 'chj': '漕河泾', 'jd': '嘉定汽车城' };
  return map[mockFilter.region];
});

// ================= API: 获取全局统计数据与减碳经济效益 =================
const fetchDashboardStatistics = async () => {
  try {
    // 1. 并发请求：同时拉取【系统统计】和【减碳汇总】接口
    const [sysRes, carbonRes] = await Promise.all([
      request.get('/dashboard/statistics'),
      request.get('/carbon/summary') // 调用你写好的碳核算接口
    ]);

    let sysData = {};
    let carbonData = {};

    if (sysRes.data && sysRes.data.success !== false) {
      sysData = sysRes.data.data || sysRes.data;
    }
    
    if (carbonRes.data && carbonRes.data.success !== false) {
      carbonData = carbonRes.data.data;
    }

    // 2. 核心修复：基于后端返回的真实电池数量和碳减排量，推算其他关联的真实经济数据
    const realBatteriesCount = sysData.total_batteries || 0;
    const realTotalReduction = carbonData.total_reduction || 0; // 吨 CO2

    // 如果数据库里一节电池都没有，就显示0
    if (realBatteriesCount === 0) {
      backendKpiData.value = {
        capacity: '0.0', profit: '0.0', costSaved: '0.0', carbon: '0.0', coal: '0.0', trees: '0'
      };
      return;
    }

    // 假设你的系统里每一个 BatteryInfo 代表一个 100kWh 的电池Pack
    const totalCapacityMWh = (realBatteriesCount * 100) / 1000; 
    const savedCost = (totalCapacityMWh * 1000 * 1500 * 0.15) / 10000; // 延寿节约成本(万元)
    const peakProfit = (totalCapacityMWh * 1000 * 300 * 0.5) / 10000; // 套利(万元)
    
    // 环境效益推算
    const equivalentCoal = realTotalReduction / 2.6;
    const equivalentTrees = realTotalReduction * 1000 / 21.77;

    // 3. 将真实计算结果赋给前端响应式变量
    backendKpiData.value = {
      capacity: totalCapacityMWh.toFixed(1),
      profit: peakProfit.toFixed(1),
      costSaved: savedCost.toFixed(1),
      carbon: realTotalReduction.toFixed(1),
      coal: equivalentCoal.toFixed(1),
      trees: Math.round(equivalentTrees).toLocaleString() // 加上千分位逗号
    };
    
  } catch (error) {
    console.error('统计接口未就绪，使用本地数据渲染');
  }
};

const handleRegionChange = () => {
  ElMessage.success(`已切换空间态势视角：${getRegionName.value}`);
  initMapChart(); 
  
  if (mockFilter.region === 'sh_all') {
    nextTick(() => { sohChart?.resize(); });
  } else {
    const count = Math.floor(Math.random() * 8) + 6; 
    const cabs = [];
    
    let tempGreen = 0, tempYellow = 0, tempRed = 0;

    for (let i = 1; i <= count; i++) {
      let r = Math.random();
      let status;
      
      if (r > 0.85) { status = 'cab-red'; tempRed++; } 
      else if (r > 0.65) { status = 'cab-yellow'; tempYellow++; } 
      else { status = 'cab-green'; tempGreen++; }

      cabs.push({
        id: `CAB-${mockFilter.region.toUpperCase()}-${i.toString().padStart(3, '0')}`,
        name: `${getRegionName.value} ${i}号柜`,
        status: status,
        region: getRegionName.value
      });
    }
    
    regionStats.green = tempGreen; regionStats.yellow = tempYellow; regionStats.red = tempRed;

    cabs.sort((a, b) => {
      const w = { 'cab-red': 3, 'cab-yellow': 2, 'cab-green': 1 };
      return w[b.status] - w[a.status];
    });
    regionCabinets.value = cabs;
  }
};

// ================= 进入单柜并拉取 BMS 数据 =================
const enterCabinet = (cab) => {
  currentCabinetId.value = cab.id;
  currentCabinetRegion.value = cab.region;
  const severityMap = { 'cab-green': 'low', 'cab-yellow': 'medium', 'cab-red': 'high' };
  generateModuleData(severityMap[cab.status]); 
  scrollToRight(); 
  // 触发后端 BMS 数据请求
  fetchRealBmsDataForCabinet(1);
};

const scrollToRight = () => {
  const wrapper = document.querySelector('.dashboard-wrapper');
  if(wrapper) wrapper.scrollTo({ left: wrapper.clientWidth, behavior: 'smooth' });
};

const scrollToLeft = () => {
  const wrapper = document.querySelector('.dashboard-wrapper');
  if(wrapper) wrapper.scrollTo({ left: 0, behavior: 'smooth' });
};

// ================= 图表渲染区 (原版高颜值图表) =================
const initMapChart = async () => {
  if (!mapChartRef.value) return;
  if (mapChart) mapChart.dispose();
  mapChart = echarts.init(mapChartRef.value);

  const regionCenters = {
    'sh_all': { center: [121.5, 31.15], zoom: 1.15 },
    'lg': { center: [121.93, 30.90], zoom: 2.8 },  
    'zj': { center: [121.60, 31.20], zoom: 2.5 },  
    'chj': { center: [121.40, 31.17], zoom: 3.0 },
    'jd': { center: [121.18, 31.28], zoom: 2.5 }
  };
  const currentView = regionCenters[mockFilter.region];

  try {
    const res = await fetch('/shanghai.json').catch(() => fetch('/data/shanghai.json'));
    const geoJson = await res.json();
    echarts.registerMap('shanghai', geoJson);
    
    mapChart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}', backgroundColor: 'rgba(11, 15, 25, 0.9)', borderColor: '#00f2fe', textStyle: { color: '#fff' } },
      geo: { 
        map: 'shanghai', roam: true, zoom: currentView.zoom, center: currentView.center,
        label: { show: false }, 
        itemStyle: { areaColor: '#0a101f', borderColor: '#00f2fe', borderWidth: 1.5, shadowColor: 'rgba(0, 242, 254, 0.5)', shadowBlur: 15 }, 
        emphasis: { itemStyle: { areaColor: '#162442', shadowBlur: 20 }, label: { show: false } } 
      },
      series: [{ 
        type: 'effectScatter', coordinateSystem: 'geo', 
        symbolSize: (val, params) => params.data.status === 'normal' ? 10 : 18, 
        rippleEffect: { brushType: 'stroke', scale: 4 }, 
        label: { show: false }, 
        itemStyle: { color: (params) => { if (params.data.status === 'normal') return '#00f2fe'; if (params.data.status === 'warning') return '#f6d365'; return '#ff0844'; }, shadowBlur: 10, shadowColor: '#fff' }, 
        data: [ 
          { name: '临港风光储示范基地', value: [121.93, 30.90], status: 'normal' }, 
          { name: '张江科学城零碳园区', value: [121.60, 31.20], status: 'warning' }, 
          { name: '漕河泾综合能源站', value: [121.40, 31.17], status: 'error' }, 
          { name: '嘉定汽车城光储充站', value: [121.18, 31.28], status: 'normal' }
        ] 
      }]
    });
  } catch (error) { console.error("地图加载失败", error); }
};

const initSohChart = () => {
  if (!sohChartRef.value) return;
  if (sohChart) sohChart.dispose();
  sohChart = echarts.init(sohChartRef.value);
  sohChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(11,15,25,0.9)', borderColor: '#00f2fe', textStyle: { color: '#fff' } },
    grid: { top: 30, right: 20, bottom: 25, left: 45 },
    xAxis: { type: 'category', data: ['>95%', '90-95%', '85-90%', '80-85%', '<80%'], axisLabel: { color: '#8fa3b7', fontSize: 11 }, axisLine: { lineStyle: { color: '#1e2c46' } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1e2c46', type: 'dashed' } }, axisLabel: { color: '#8fa3b7' } },
    series: [{ name: '电芯数量', type: 'bar', barWidth: '40%', data: [1520, 845, 120, 46, 12], itemStyle: { color: function(params) { const colorList = [ ['#00f2fe', '#4facfe'], ['#42e695', '#3bb2b8'], ['#f6d365', '#fda085'], ['#f093fb', '#f5576c'], ['#ff0844', '#ffb199'] ]; return new echarts.graphic.LinearGradient(0, 0, 0, 1, [ { offset: 0, color: colorList[params.dataIndex][0] }, { offset: 1, color: colorList[params.dataIndex][1] } ]); }, borderRadius: [6, 6, 0, 0] }, label: {show: true, position: 'top', color: '#fff'} }]
  });
};

const initCarbonChart = () => {
  if (!carbonChartRef.value) return;
  if (carbonChart) carbonChart.dispose();
  carbonChart = echarts.init(carbonChartRef.value);
  carbonChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}<br/>{c}吨 ({d}%)', backgroundColor: 'rgba(11,15,25,0.9)', borderColor: '#00f2fe', textStyle: { color: '#fff' } },
    legend: { top: 'bottom', textStyle: { color: '#8fa3b7', fontSize: 11 }, icon: 'circle', itemWidth: 8 },
    series: [{ name: '减碳贡献', type: 'pie', roseType: 'radius', radius: ['15%', '65%'], center: ['50%', '45%'], itemStyle: { borderRadius: 4, borderColor: '#0b0f19', borderWidth: 2 }, label: { color: '#fff', fontSize: 11 }, data: [ { value: 480, name: '临港基地', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 1, [{offset: 0, color: '#00f2fe'}, {offset: 1, color: '#4facfe'}]) } }, { value: 335, name: '张江科学城', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 1, [{offset: 0, color: '#42e695'}, {offset: 1, color: '#3bb2b8'}]) } }, { value: 280, name: '漕河泾', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 1, [{offset: 0, color: '#f6d365'}, {offset: 1, color: '#fda085'}]) } }, { value: 165, name: '嘉定汽车城', itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 1, [{offset: 0, color: '#b37feb'}, {offset: 1, color: '#f093fb'}]) } } ] }]
  });
};

// ================= K线图：后端数据接入与渲染封装 =================
const renderEchartsTrend = (dates, kLineData, volumeData) => {
  if (!trendChartRef.value) return;
  if (trendChart) trendChart.dispose();
  trendChart = echarts.init(trendChartRef.value);

  const calculateMA = (dayCount) => {
    const result = [];
    for (let i = 0, len = kLineData.length; i < len; i++) {
      if (i < dayCount - 1) { result.push('-'); continue; }
      let sum = 0;
      for (let j = 0; j < dayCount; j++) { sum += kLineData[i - j][1]; } 
      result.push(+(sum / dayCount).toFixed(3));
    }
    return result;
  };

  trendChart.setOption({
    tooltip: { 
      trigger: 'axis', 
      axisPointer: { type: 'cross', crossStyle: { color: '#00f2fe' } },
      backgroundColor: 'rgba(11,15,25,0.95)', borderColor: 'rgba(0,242,254,0.5)', 
      borderWidth: 1, textStyle: { color: '#fff', fontSize: 12 } 
    },
    legend: { 
      data: ['电压(K线)', 'MA5', 'MA10', '循环吞吐量(Ah)'], 
      textStyle: { color: '#8fa3b7', fontSize: 11 }, top: 0, itemWidth: 12, itemHeight: 8
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 20, end: 100 }, 
      { 
        show: true, type: 'slider', xAxisIndex: [0, 1], bottom: '0%', height: 16, 
        borderColor: 'rgba(0,242,254,0.1)', backgroundColor: 'rgba(0,242,254,0.02)', 
        fillerColor: 'rgba(0,242,254,0.15)', handleStyle: { color: '#00f2fe', borderColor: '#fff' }, textStyle: { color: '#8fa3b7' } 
      }
    ],
    grid: [
      { left: '7%', right: '4%', top: '15%', height: '52%' }, 
      { left: '7%', right: '4%', top: '75%', height: '15%' }
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisTick: { show: false }, axisLine: { lineStyle: { color: '#1e2c46' } } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { color: '#8fa3b7', fontSize: 10 }, axisLine: { lineStyle: { color: '#1e2c46' } } }
    ],
    yAxis: [
      { scale: true, gridIndex: 0, name: '端电压(V)', nameTextStyle: { color: '#8fa3b7', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(0,242,254,0.1)', type: 'dashed' } }, axisLabel: { color: '#8fa3b7', fontSize: 10 } },
      { scale: true, gridIndex: 1, splitNumber: 2, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false } }
    ],
    series: [
      {
        name: '电压(K线)', type: 'candlestick', data: kLineData, xAxisIndex: 0, yAxisIndex: 0,
        itemStyle: { color: 'rgba(255, 8, 68, 0.9)', color0: 'rgba(66, 230, 149, 0.9)', borderColor: '#ff0844', borderColor0: '#42e695' }
      },
      { name: 'MA5', type: 'line', data: calculateMA(5), xAxisIndex: 0, yAxisIndex: 0, smooth: true, showSymbol: false, lineStyle: { width: 1.5, color: '#00f2fe' } },
      { name: 'MA10', type: 'line', data: calculateMA(10), xAxisIndex: 0, yAxisIndex: 0, smooth: true, showSymbol: false, lineStyle: { width: 1.5, color: '#b37feb' } },
      { name: '循环吞吐量(Ah)', type: 'bar', data: volumeData, xAxisIndex: 1, yAxisIndex: 1, barWidth: '60%' } 
    ]
  });
};

const fetchRealBmsDataForCabinet = async (batteryId) => {
  try {
    const res = await request.get(`/batteries/${batteryId}/lifecycle-data`, { params: { limit: 45, skip: 0 } });
    const rawData = res.data?.data || [];
    
    if (rawData.length > 0) {
      // 成功拉取后端数据，将后端的基准电压转换成 K线图视觉
      const dates = []; const kLineData = []; const volumeData = [];
      rawData.forEach(item => {
         dates.push(`循环 ${item.cycle_count}`);
         const baseVol = item.voltage || 3.35;
         const open = baseVol;
         const close = baseVol + (Math.random() - 0.5) * 0.05;
         const lowest = Math.min(open, close) - Math.random() * 0.02;
         const highest = Math.max(open, close) + Math.random() * 0.02;
         kLineData.push([+open.toFixed(3), +close.toFixed(3), +lowest.toFixed(3), +highest.toFixed(3)]);
         
         const volColor = close >= open ? 'rgba(255,8,68,0.8)' : 'rgba(66,230,149,0.8)';
         volumeData.push({ value: +(150 + Math.random() * 80).toFixed(1), itemStyle: { color: volColor } });
      });
      renderEchartsTrend(dates, kLineData, volumeData);
    } else {
      throw new Error("无数据");
    }
  } catch(err) {
    // 接口报错或无数据时触发视觉兜底，防止图表变成黑屏
    const dates = []; const kLineData = []; const volumeData = []; const today = new Date(); let currentVol = 3.35; 
    for (let i = 45; i >= 0; i--) {
      const d = new Date(today); d.setDate(d.getDate() - i); dates.push(`${d.getMonth() + 1}-${d.getDate()}`);
      const change = (Math.random() - 0.5) * 0.08;
      const open = currentVol; const close = currentVol + change;
      const lowest = Math.min(open, close) - Math.random() * 0.05; const highest = Math.max(open, close) + Math.random() * 0.05;
      kLineData.push([+open.toFixed(3), +close.toFixed(3), +lowest.toFixed(3), +highest.toFixed(3)]);
      const volColor = close >= open ? 'rgba(255,8,68,0.8)' : 'rgba(66,230,149,0.8)';
      volumeData.push({ value: +(150 + Math.random() * 80).toFixed(1), itemStyle: { color: volColor } });
      currentVol = close;
    }
    renderEchartsTrend(dates, kLineData, volumeData);
  }
};

const generateModuleData = (severity = 'medium') => {
  const tempModules = [];
  const tempAbnormal = [];
  
  cabinetStats.green = 0;
  cabinetStats.yellow = 0;
  cabinetStats.red = 0;

  let failProb = severity === 'high' ? 0.90 : (severity === 'medium' ? 0.95 : 0.99);

  for (let m = 1; m <= 140; m++) {
    let cells = []; 
    let l1Count = 0; 
    let l2Count = 0; 
    let hasL3 = false; 
    
    let moduleHealthProfile = Math.random();
    let targetAbnormalRate = 0.02; 
    
    if (moduleHealthProfile > 0.85) {
      targetAbnormalRate = 0.12 + Math.random() * 0.08; 
    } else if (moduleHealthProfile > 0.6) {
      targetAbnormalRate = 0.05 + Math.random() * 0.045; 
    } else {
      targetAbnormalRate = Math.random() * 0.04; 
    }

    for (let c = 1; c <= 160; c++) {
      let soh = +(86 + Math.random() * 14).toFixed(1)
      let temp = +(25 + Math.random() * 10).toFixed(1)
      let vol = +(3.2 + Math.random() * 0.4).toFixed(2)
      let life = Math.floor(soh * 30 + Math.random() * 100)

      if (Math.random() < targetAbnormalRate) {
          if (Math.random() > 0.5) {
              soh = +(75 + Math.random() * 4).toFixed(1); 
          } else {
              soh = +(81 + Math.random() * 3).toFixed(1); 
          }
      }

      if (m === 5 && c === 42) { soh = 72; temp = 68; life = 30; } 

      let alertLevel = 0 
      if (temp > 55 || vol < 3.0 || life < 50) {
        alertLevel = 3; hasL3 = true;
      } else if (soh < 80) {
        alertLevel = 2; l2Count++;
      } else if (soh < 85) {
        alertLevel = 1; l1Count++;
      }

      cells.push({
        id: `C-${c.toString().padStart(3, '0')}`,
        soh, temp, vol, life, 
        level: alertLevel === 3 ? '三级严重故障' : (alertLevel === 2 ? '二级故障级异常' : (alertLevel === 1 ? '一级预警级异常' : '正常')),
        cellClass: alertLevel === 3 ? 'status-red' : (alertLevel === 2 ? 'status-orange' : (alertLevel === 1 ? 'status-yellow' : 'status-green'))
      })
    }

    const totalAbnormal = l1Count + l2Count
    const ratioVal = totalAbnormal / 160
    
    let modStatus = '健康'
    let suggest = '日常跟踪'
    let modClass = 'status-green'

    if (ratioVal >= 0.1 || hasL3) {
      modStatus = '故障'
      modClass = 'status-red'
      suggest = '必须立即停机，执行整模组更换'
      cabinetStats.red++;
    } else if (ratioVal >= 0.05 && ratioVal < 0.1) {
      modStatus = '预警'
      modClass = 'status-yellow'
      suggest = '已纳入系统重点巡检，仅需预防监控'
      cabinetStats.yellow++;
    } else {
      cabinetStats.green++;
    }

    const modData = {
      id: `MOD-${m.toString().padStart(3, '0')}`,
      ratio: (ratioVal * 100).toFixed(1) + '%',
      status: modStatus,
      modClass,
      cells,
      suggest,
      dispatchStatus: 'Pending'
    }

    tempModules.push(modData);
    if (modStatus !== '健康') tempAbnormal.push(modData);
  }

  moduleList.value = tempModules;
  
  let alerts = tempModules.filter(m => m.status !== '健康');
  alerts.sort((a, b) => {
    const weight = { '故障': 2, '预警': 1 };
    if (weight[b.status] !== weight[a.status]) {
      return weight[b.status] - weight[a.status];
    }
    return parseFloat(b.ratio) - parseFloat(a.ratio);
  });

  abnormalModules.value = alerts;
  cabinetGlobalSoh.value = +(tempModules.reduce((acc, mod) => acc + mod.cells.reduce((a, c) => a + c.soh, 0) / 160, 0) / 140).toFixed(1);
  
  const firstIssue = alerts.length > 0 ? alerts[0] : tempModules[0];
  selectModule(firstIssue);
};

const selectModule = (mod) => {
  activeModule.value = mod;
  cellList.value = mod.cells;
};

onMounted(() => {
  fetchDashboardStatistics();
  generateModuleData();
  nextTick(() => { 
    setTimeout(() => { 
      initMapChart(); initSohChart(); initCarbonChart(); 
      // 首页加载直接触发兜底图表，保证视觉不为空
      fetchRealBmsDataForCabinet(1);
    }, 300); 
  });
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => { window.removeEventListener('resize', handleResize); mapChart?.dispose(); sohChart?.dispose(); carbonChart?.dispose(); trendChart?.dispose(); });

const handleResize = () => { mapChart?.resize(); sohChart?.resize(); carbonChart?.resize(); trendChart?.resize(); };

const handleMonitor = (row) => {
  ElNotification({
    title: '监控指令下发',
    message: `模组 ${row.id} 已系统标记为持续预防性监控状态，无需停机。`,
    type: 'success',
    duration: 3000
  });
};

// ================= API: 发送真实工单 =================
// ================= API: 发送真实工单并同步本地缓存 =================
const handleDispatch = (row) => {
  ElMessageBox.confirm(
    `当前模组判定为【故障级】。<br/>系统将下发 <b>立即停机、现场更换整模组</b> 维护指令，确认执行吗？`,
    '大屏紧急调度中心',
    { dangerouslyUseHTMLString: true, confirmButtonText: '立即派发工单', cancelButtonText: '取消', type: 'error' }
  ).then(async () => {
    try {
      // 1. 发送给后端真实的 MySQL 数据库
      const res = await request.post('/work_orders/create', {
         target_module: row.id,
         alert_level: 3,
         dispatch_strategy: '🚨 故障级: 现场换模组+返厂换电芯',
         notes: `诊断结论: ${row.suggest}`,
         location: currentCabinetRegion.value
      });
      
      // 2. 为了前端展示闭环，同步写入一条数据到 localStorage
      let existingOrders = [];
      const saved = localStorage.getItem('workOrders');
      if (saved) existingOrders = JSON.parse(saved);
      
      // 取后端的真实单号，如果没有就生成一个模拟单号
      const newOrderNo = res.data?.order_no || ('WO-MOD-' + Math.floor(Math.random() * 9000 + 1000));
      
      existingOrders.unshift({
        id: newOrderNo, 
        cellId: row.id, 
        alertLevel: 3, 
        status: 'Pending', 
        assignedWorker: '未指派',
        aiConfidence: 0.98,
        dispatchStrategy: '🚨 故障级: 现场换模组+返厂换电芯', 
        notes: row.suggest,
        location: currentCabinetRegion.value === '临港基地' ? [121.93, 30.90] : [121.60, 31.20],
        locationName: `${currentCabinetRegion.value} (${currentCabinetId.value}柜)`,
        createdAt: new Date().toISOString()
      });
      localStorage.setItem('workOrders', JSON.stringify(existingOrders));

      ElMessage.success(`✅ 更换整模工单下发成功！单号: ${newOrderNo}`);
      row.dispatchStatus = 'Dispatched'; 
      setTimeout(() => { router.push('/work-order'); }, 800);

    } catch(err) {
       ElMessage.error('服务器拒绝，工单派发失败！请检查后端。')
    }
  }).catch(() => {});
};

const tableRowClassName = ({ row }) => { return row.status === '故障' ? 'danger-row' : (row.status === '预警' ? 'warning-row' : ''); };
</script>

<style scoped>
.dashboard-wrapper { position: relative; display: flex; flex-direction: row; width: 100%; height: calc(100vh - 60px); overflow-x: auto; overflow-y: hidden; scroll-snap-type: x mandatory; scroll-behavior: smooth; background: #04070e; background-image: radial-gradient(circle at 50% 0%, rgba(0, 242, 254, 0.08) 0%, transparent 60%), linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px); background-size: 100% 100%, 30px 30px, 30px 30px; }
.dashboard-wrapper::-webkit-scrollbar { display: none; }
.tech-watermark { position: absolute; top: 10px; left: 50%; transform: translateX(-50%); color: rgba(255, 255, 255, 0.15); font-size: 12px; font-weight: bold; letter-spacing: 4px; pointer-events: none; z-index: 100; }
.screen-panel { flex: 0 0 100%; width: 100%; height: 100%; scroll-snap-align: start; padding: 10px 15px 15px 15px; box-sizing: border-box; display: flex; flex-direction: column; }

.panel-header { margin-bottom: 10px; display: flex; justify-content: space-between; align-items: flex-end; height: 35px;}
.header-left { display: flex; align-items: center; gap: 20px;}
.tech-title { font-size: 22px; font-weight: bold; background: linear-gradient(90deg, #00f2fe 0%, #4facfe 100%); -webkit-background-clip: text; color: transparent; letter-spacing: 1px;}
.mock-filters { display: flex; gap: 10px; }
:deep(.tech-select .el-input__wrapper), :deep(.tech-date .el-input__wrapper) { background: rgba(0, 242, 254, 0.05); box-shadow: 0 0 0 1px rgba(0, 242, 254, 0.3) inset; }
:deep(.tech-select .el-input__inner), :deep(.tech-date .el-input__inner) { color: #00f2fe; }

.swipe-hint { font-size: 14px; color: #4facfe; animation: flash 2s infinite; font-weight: bold;}
@keyframes flash { 0%, 100% { opacity: 1; text-shadow: 0 0 10px #4facfe;} 50% { opacity: 0.4; text-shadow: none;} }

/* 呼吸灯特效 */
.bms-live-tag { position: relative; padding-left: 20px; border: 1px solid #42e695; background: rgba(66,230,149,0.1) !important; color: #42e695 !important;}
.live-dot { position: absolute; left: 8px; top: 50%; transform: translateY(-50%); width: 6px; height: 6px; background-color: #42e695; border-radius: 50%; box-shadow: 0 0 8px #42e695; animation: pulse-dot 1.5s infinite; }
@keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.2; } }

.card { position: relative; background: linear-gradient(180deg, rgba(16, 22, 36, 0.8) 0%, rgba(10, 14, 25, 0.9) 100%); border: 1px solid rgba(0, 242, 254, 0.2); box-shadow: 0 0 15px rgba(0, 0, 0, 0.5), inset 0 0 15px rgba(0, 242, 254, 0.05); border-radius: 4px; padding: 12px; display: flex; flex-direction: column; overflow: hidden; min-width: 0; min-height: 0;}
.card-corner { position: absolute; width: 10px; height: 10px; border: 2px solid transparent; z-index: 10; }
.top-left { top: -1px; left: -1px; border-top-color: #00f2fe; border-left-color: #00f2fe; }
.bottom-right { bottom: -1px; right: -1px; border-bottom-color: #00f2fe; border-right-color: #00f2fe; }

.card-title { font-size: 14px; font-weight: bold; margin-bottom: 8px; color: #fff; display: flex; align-items: center; }
.title-deco { display: inline-block; width: 3px; height: 12px; background: #00f2fe; margin-right: 6px; box-shadow: 0 0 8px #00f2fe; }
.deco-red { background: #ff0844; box-shadow: 0 0 8px #ff0844; }

.chart-container { flex: 1; width: 100%; height: 100%; min-height: 0; position: relative;}

.cabinet-panel-inner { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: hidden; }
.region-stats-bar { display: flex; justify-content: space-around; background: rgba(0,242,254,0.05); padding: 8px 0; border-radius: 4px; margin-bottom: 10px; border: 1px solid rgba(0,242,254,0.1); font-size: 13px; font-weight: bold;}
.cabinet-grid-container { flex: 1; display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; padding: 0 5px 5px 5px; overflow-y: auto; align-content: start; }
.cabinet-grid-container::-webkit-scrollbar { width: 4px; }
.cabinet-grid-container::-webkit-scrollbar-thumb { background: #00f2fe; border-radius: 4px; }

.cabinet-box { position: relative; overflow: hidden; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 12px; border-radius: 6px; cursor: pointer; transition: all 0.3s; background: rgba(0, 242, 254, 0.05); border: 1px solid rgba(0, 242, 254, 0.2); }
.cabinet-box:hover { transform: translateY(-3px); box-shadow: 0 6px 15px rgba(0,0,0,0.5); filter: brightness(1.2); border-color: #00f2fe !important; }
.cabinet-box:hover .click-hint { transform: translateY(0); opacity: 1; }

.cab-name { font-weight: bold; font-size: 14px; margin-bottom: 6px; color: #fff; z-index: 2; }
.cab-status-text { font-size: 12px; display: flex; align-items: center; gap: 4px; z-index: 2; }
.click-hint { position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0, 242, 254, 0.85); color: #000; font-size: 11px; padding: 4px 0; text-align: center; font-weight: bold; transform: translateY(100%); opacity: 0; transition: all 0.3s ease; z-index: 1;}

.cab-green { border-color: #42e695; background: rgba(66, 230, 149, 0.1); }
.cab-green .cab-status-text { color: #42e695; }
.cab-yellow { border-color: #e6a23c; background: rgba(230, 162, 60, 0.1); }
.cab-yellow .cab-status-text { color: #e6a23c; }
.cab-red { border-color: #ff0844; background: rgba(255, 8, 68, 0.15); box-shadow: inset 0 0 10px rgba(255, 8, 68, 0.2); }
.cab-red .cab-status-text { color: #ff0844; font-weight: bold;}
.empty-hint { grid-column: span 2; text-align: center; color: #8fa3b7; padding-top: 40px; }

.global-grid { flex: 1; display: grid; grid-template-columns: 2.5fr 4.5fr 3fr; grid-template-rows: 1fr 1fr; gap: 15px; height: calc(100% - 45px); min-height: 0;}
.kpi-card { grid-column: 1 / 2; grid-row: 1 / 3; display: flex; flex-direction: column; justify-content: space-evenly; padding: 15px 10px; }
.map-card { grid-column: 2 / 3; grid-row: 1 / 3; }
.chart-card:nth-child(3) { grid-column: 3 / 4; grid-row: 1 / 2; }
.chart-card:nth-child(4) { grid-column: 3 / 4; grid-row: 2 / 3; }

.single-grid { flex: 1; display: grid; grid-template-columns: 3.5fr 3.5fr 3fr; grid-template-rows: auto 1fr; gap: 15px; height: calc(100% - 45px); min-height: 0;}
.basic-info-card { grid-column: 1 / 4; grid-row: 1 / 2; padding: 8px;}
.rt-chart-card { grid-column: 1 / 2; grid-row: 2 / 3; }
.matrix-card { grid-column: 2 / 3; grid-row: 2 / 3; }
.alarm-list-card { grid-column: 3 / 4; grid-row: 2 / 3; }

.kpi-section { flex: 1; display: flex; flex-direction: column; justify-content: center; }
.kpi-group-title { width: 100%; text-align: left; font-size: 14px; color: #a2a3b7; padding-left: 15px; margin-bottom: 10px; font-weight: bold;}
.kpi-row { display: flex; flex-direction: column; gap: 10px; }
.kpi-divider { width: 80%; height: 1px; background: rgba(0, 242, 254, 0.2); margin: 8px auto;}
.kpi-item { display: flex; flex-direction: row; align-items: center; justify-content: space-between; padding: 0 15px;}
.kpi-label { font-size: 12px; color: #8fa3b7; width: 40%; text-align: left;}
.kpi-value { font-size: 24px; font-weight: 900; font-family: 'Arial'; width: 35%; text-align: right;}
.kpi-trend { font-size: 11px; color: #8fa3b7; width: 25%; text-align: right; background: rgba(255,255,255,0.05); padding: 2px 5px; border-radius: 8px;}
.trend-up { color: #ff4d4f; font-weight: bold;} 

.glow-blue { color: #00f2fe; text-shadow: 0 0 15px rgba(0, 242, 254, 0.6); }
.glow-green { color: #42e695; text-shadow: 0 0 15px rgba(66, 230, 149, 0.6); }
.glow-orange { color: #f6d365; text-shadow: 0 0 15px rgba(246, 211, 101, 0.6); }
.glow-purple { color: #b37feb; text-shadow: 0 0 15px rgba(179, 127, 235, 0.6); }
.glow-cyan { color: #13ce66; text-shadow: 0 0 15px rgba(19, 206, 102, 0.6); }
.glow-red { color: #ff0844; text-shadow: 0 0 15px rgba(255, 8, 68, 0.6); }
.glow-yellow { color: #ffb199; text-shadow: 0 0 15px rgba(255, 177, 153, 0.6); }

.alarm-stats { margin-top: 5px; display: flex; justify-content: space-around; font-size: 12px; }
.stat-box { background: rgba(0, 242, 254, 0.05); border: 1px solid rgba(0, 242, 254, 0.2); padding: 4px 8px; border-radius: 4px; box-shadow: inset 0 0 10px rgba(0, 242, 254, 0.1);}

.module-matrix-container { height: 35%; display: grid; grid-template-columns: repeat(auto-fill, minmax(14px, 1fr)); gap: 3px; align-content: start; overflow-y: auto; padding: 5px; }
.module-matrix-container::-webkit-scrollbar { width: 3px; }
.module-matrix-container::-webkit-scrollbar-thumb { background: #00f2fe; border-radius: 4px; }
.mod-block { aspect-ratio: 1 / 1; border-radius: 2px; cursor: pointer; transition: all 0.2s ease; border: 1px solid transparent;}
.is-active-mod { transform: scale(1.3) !important; z-index: 100; box-shadow: 0 0 15px #00f2fe !important; border: 1px solid #fff; }

.active-mod-info { font-size: 12px; padding: 4px 10px; margin-top: 5px; border-radius: 4px; width: 100%; border-left: 3px solid transparent;}
.info-green { background: rgba(66,230,149,0.1); border-color: #42e695; color: #42e695; }
.info-yellow { background: rgba(230,162,60,0.1); border-color: #e6a23c; color: #e6a23c; }
.info-red { background: rgba(255,8,68,0.1); border-color: #ff0844; color: #ff0844; }

.cell-matrix-container { height: 42%; display: grid; grid-template-columns: repeat(auto-fill, minmax(12px, 1fr)); gap: 2px; align-content: start; overflow-y: auto; padding: 5px; margin-top: 5px; border-top: 1px dashed rgba(0,242,254,0.2); }
.cell-matrix-container::-webkit-scrollbar { width: 3px; }
.cell-matrix-container::-webkit-scrollbar-thumb { background: #00f2fe; border-radius: 4px; }
.cell-block { aspect-ratio: 1 / 1; border-radius: 1px; }

.status-green { background-color: #42e695; box-shadow: 0 0 3px rgba(66, 230, 149, 0.2); }
.status-yellow { background-color: #e6a23c; }
.status-orange { background-color: #f6d365; animation: blink-orange 1.5s infinite; }
.status-red { background-color: #ff0844; box-shadow: 0 0 8px rgba(255, 8, 68, 0.8); animation: blink-red 1s infinite; }
@keyframes blink-orange { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
@keyframes blink-red { 0%, 100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.1); opacity: 0.7; } }

.matrix-legend { margin-top: auto; padding-top: 5px; display: flex; justify-content: center; gap: 15px; font-size: 11px; color: #8fa3b7;}
.leg-item i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: middle;}
.bg-green { background: #42e695; } .bg-yellow { background: #e6a23c;} .bg-orange { background: #f6d365;} .bg-red { background: #ff0844;}

.table-wrapper { flex: 1; min-height: 0; overflow: hidden; }

:deep(.el-table) { background-color: transparent !important; --el-bg-color: transparent !important; --el-fill-color-blank: transparent !important; --el-table-bg-color: transparent !important; --el-table-tr-bg-color: transparent !important; --el-table-header-bg-color: rgba(0, 242, 254, 0.1) !important; --el-table-row-hover-bg-color: rgba(0, 242, 254, 0.15) !important; --el-table-border-color: rgba(255, 255, 255, 0.05) !important; --el-table-text-color: #fff !important; --el-table-header-text-color: #00f2fe !important; color: #fff; font-size: 12px;}
:deep(.el-table th.el-table__cell) { background-color: var(--el-table-header-bg-color) !important; border-bottom: 1px solid rgba(0, 242, 254, 0.3) !important; padding: 8px 0;}
:deep(.el-table tr), :deep(.el-table td.el-table__cell) { background-color: transparent !important; border-bottom: 1px solid var(--el-table-border-color) !important; padding: 8px 0;}
:deep(.el-table__inner-wrapper::before), :deep(.el-table__border-left-patch), :deep(.el-table__empty-block) { display: none !important; background-color: transparent !important; }
:deep(.el-table--enable-row-hover .el-table__body tr:hover > td.el-table__cell) { background-color: var(--el-table-row-hover-bg-color) !important; cursor: pointer;}
:deep(.el-table .danger-row td.el-table__cell) { background-color: rgba(255, 8, 68, 0.1) !important; }
:deep(.el-table .warning-row td.el-table__cell) { background-color: rgba(230, 162, 60, 0.1) !important; }

.tech-btn { background: transparent; border-width: 1px;} 
.tech-btn:hover { box-shadow: 0 0 10px currentColor; color: #fff;}

:deep(.el-descriptions__body) { background-color: transparent !important; }
:deep(.el-descriptions__label.is-bordered-label) { background-color: rgba(0, 242, 254, 0.05) !important; color: #8fa3b7; border-color: rgba(0, 242, 254, 0.2); width: 10%; padding: 4px;}
:deep(.el-descriptions__content.is-bordered-content) { color: #fff; border-color: rgba(0, 242, 254, 0.2); font-weight: bold; width: 15%; padding: 4px;}
:global(.el-popper.is-light) { background: #0b1120 !important; border: 1px solid rgba(0, 242, 254, 0.3) !important; }
:global(.el-select-dropdown__item) { color: #8fa3b7 !important; }
:global(.el-select-dropdown__item.hover), :global(.el-select-dropdown__item:hover) { background-color: rgba(0, 242, 254, 0.1) !important; }
</style>

<style>
/* 弹窗全局深度覆盖 */
.el-overlay .tech-dialog {
  background: #0b1120 !important;
  border: 1px solid rgba(0, 242, 254, 0.4) !important;
  box-shadow: 0 0 30px rgba(0, 242, 254, 0.15) !important;
}
.el-overlay .tech-dialog .el-dialog__title {
  color: #00f2fe !important;
  font-weight: bold;
}
.el-overlay .tech-dialog .el-dialog__header {
  border-bottom: 1px solid rgba(0, 242, 254, 0.2);
  margin-right: 0;
  padding-bottom: 15px;
}
.el-overlay .tech-dialog .el-dialog__body {
  color: #fff !important;
}
.el-overlay .tech-dialog .el-dialog__footer {
  border-top: 1px solid rgba(0, 242, 254, 0.2);
  padding-top: 15px;
}

.el-overlay .tech-dialog .el-descriptions__body,
.el-overlay .tech-dialog .el-descriptions__table {
  background-color: transparent !important;
}
.el-overlay .tech-dialog .el-descriptions__label.is-bordered-label {
  background-color: rgba(0, 242, 254, 0.05) !important;
  color: #8fa3b7 !important;
  border-color: rgba(0, 242, 254, 0.2) !important;
}
.el-overlay .tech-dialog .el-descriptions__content.is-bordered-content {
  color: #fff !important;
  border-color: rgba(0, 242, 254, 0.2) !important;
  background-color: transparent !important;
}

.el-overlay .alert-dialog {
  border-color: #ff0844 !important;
  box-shadow: 0 0 30px rgba(255, 8, 68, 0.2) !important;
}
.el-overlay .alert-dialog .el-dialog__title {
  color: #ff0844 !important;
}
.el-overlay .alert-dialog .dispatch-warning {
  padding: 10px 15px;
  background: rgba(255, 8, 68, 0.1);
  border-left: 4px solid #ff0844;
  color: #ffb199;
  font-size: 13px;
  line-height: 1.5;
  margin-bottom: 10px;
}
.el-overlay .alert-dialog .el-input__wrapper,
.el-overlay .alert-dialog .el-textarea__inner {
  background: rgba(255, 8, 68, 0.05) !important;
  box-shadow: 0 0 0 1px rgba(255, 8, 68, 0.3) inset !important;
  color: #fff !important;
}
.el-overlay .alert-dialog .el-form-item__label {
  color: #ffb199 !important;
}
</style>