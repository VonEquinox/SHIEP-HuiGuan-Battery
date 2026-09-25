<template>
  <div class="work-order-wrapper">
    <div class="tech-watermark">AI-Driven Operation & Maintenance Dispatch Center</div>

    <header class="panel-header">
      <div class="header-left">
        <span class="tech-title">智能运维与工单调度中心</span>
        <el-tag effect="dark" type="success" class="live-tag">
          <span class="live-dot"></span> 实时调度网在线
        </el-tag>
      </div>
      <div class="header-right">
        <div class="time-display">{{ currentTime }}</div>
        <el-button type="primary" plain class="tech-btn-back" @click="returnToDashboard">
          <el-icon><Monitor /></el-icon> 返回监控大屏
        </el-button>
      </div>
    </header>

    <div class="main-content-grid">
      <div class="stats-row">
        <div class="stat-card">
          <div class="card-corner top-left"></div><div class="card-corner bottom-right"></div>
          <div class="stat-icon warning"><el-icon><Bell /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value glow-yellow">{{ pendingOrders }}</div>
            <div class="stat-label">待指派工单</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="card-corner top-left"></div><div class="card-corner bottom-right"></div>
          <div class="stat-icon processing"><el-icon><Guide /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value glow-blue">{{ processingOrders }}</div>
            <div class="stat-label">执行中/待验收</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="card-corner top-left"></div><div class="card-corner bottom-right"></div>
          <div class="stat-icon danger"><el-icon><Warning /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value glow-red">{{ exceptionOrders }}</div>
            <div class="stat-label">异常挂起</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="card-corner top-left"></div><div class="card-corner bottom-right"></div>
          <div class="stat-icon success"><el-icon><CircleCheck /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value glow-green">{{ resolvedOrders }}</div>
            <div class="stat-label">已闭环工单</div>
          </div>
        </div>
      </div>

      <div class="data-table-container tech-box">
        <div class="table-header-ops">
          <el-radio-group v-model="statusFilter" class="tech-radio-group" size="small">
            <el-radio-button value="all">全部工单</el-radio-button>
            <el-radio-button value="Pending">待指派</el-radio-button>
            <el-radio-button value="Processing">执行中</el-radio-button>
            <el-radio-button value="Review">待验收</el-radio-button>
            <el-radio-button value="Resolved">已闭环</el-radio-button>
          </el-radio-group>
        </div>

        <el-table 
          :data="sortedOrders" 
          height="100%" 
          style="width: 100%" 
          class="tech-table" 
          :row-class-name="tableRowClassName"
        >
          <el-table-column prop="id" label="工单编号" width="140">
            <template #default="scope">
              <span class="order-id">{{ scope.row.id }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="cellId" label="关联模组/电芯" width="180">
            <template #default="scope">
              <span class="cell-id-link"><el-icon><DataLine /></el-icon> {{ scope.row.cellId }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="alertLevel" label="故障定级" width="140" align="center">
            <template #default="scope">
              <el-tag :type="getAlertType(scope.row.alertLevel)" effect="dark" class="level-tag">
                {{ getAlertLabel(scope.row.alertLevel) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="dispatchStrategy" label="AI 辅助决策策略" min-width="250">
            <template #default="scope">
              <div class="strategy-col">
                <span class="strategy-text">{{ scope.row.dispatchStrategy || '自动诊断策略' }}</span>
                <el-tooltip content="AI 模型诊断置信度" placement="top" effect="dark">
                  <span class="confidence" :class="{'high': (scope.row.aiConfidence || 0.985) > 0.95}">
                    {{ ((scope.row.aiConfidence || 0.985) * 100).toFixed(1) }}%
                  </span>
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
          
          <el-table-column prop="assignedWorker" label="指派人员" width="120" align="center">
            <template #default="scope">
              <span v-if="scope.row.status !== 'Pending' && scope.row.assignedWorker !== '未指派'" class="worker-name">
                <el-icon><UserFilled /></el-icon>
                {{ scope.row.assignedWorker }}
              </span>
              <span v-else class="empty-placeholder">--</span>
            </template>
          </el-table-column>
          
          <el-table-column prop="status" label="流程状态" width="130" align="center">
            <template #default="scope">
              <span class="status-indicator" :class="getStatusClass(scope.row.status)">
                <span class="status-dot"></span> {{ getStatusText(scope.row.status) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right" align="center">
            <template #default="scope">
              <el-button v-if="scope.row.status === 'Pending'" size="small" type="primary" plain class="op-btn" @click="openAssignDialog(scope.row)">
                一键派单
              </el-button>
              <el-button v-if="scope.row.status === 'Processing'" size="small" type="warning" plain class="op-btn" @click="openExecuteDialog(scope.row)">
                现场录入
              </el-button>
              <el-button v-if="scope.row.status === 'Processing'" size="small" type="danger" link @click="openExceptionDialog(scope.row)">
                异常挂起
              </el-button>
              <el-button v-if="scope.row.status === 'Review'" size="small" type="success" plain class="op-btn" @click="openReviewDialog(scope.row)">
                管理验收
              </el-button>
              <el-button v-if="scope.row.status === 'Resolved' || scope.row.status === 'Exception'" size="small" type="info" plain class="op-btn" @click="viewWorkOrderDetails(scope.row)">
                查看详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="assignDialogVisible" title="AI 多维智能派单中枢" width="850px" class="tech-dialog" custom-class="tech-dialog" @opened="initMiniMap" destroy-on-close>
      
      <div class="assign-task-header" v-if="currentWorkOrder">
        <div class="task-node-info">
          <el-icon><Location /></el-icon>
          <span class="task-text">任务节点: {{ currentWorkOrder.locationName || '现场节点' }} ({{ currentWorkOrder.cellId }})</span>
          <span class="task-badge">故障级换模任务</span>
        </div>
      </div>

      <div class="assign-warning-banner" v-if="currentWorkOrder && currentWorkOrder.alertLevel === 3">
        <el-icon><WarningFilled /></el-icon>
        <span>【系统强制风控】判定为模组级严重故障！必须派发具备高级电工资质的人员执行「停机换模」操作，要求双人同行。</span>
      </div>

      <div class="assign-container">
        <div class="assign-left">
          <div class="panel-subtitle">时空孪生: 点击蓝标人员一键调度</div>
          <div class="map-box" ref="miniMapRef"></div>
        </div>
        <div class="assign-right">
          <div class="panel-subtitle">算法寻优候选项库 (基于人岗/负载匹配)</div>
          <div class="recommendation-list">
            <div 
              v-for="worker in recommendedWorkers" 
              :key="worker.id"
              class="worker-card"
              :class="{ 'is-selected': assignForm.worker === worker.name }"
              @click="selectWorker(worker)"
            >
              <div class="worker-header">
                <span class="w-name"><el-icon class="avatar-icon"><UserFilled /></el-icon> {{ worker.name }}</span>
                <span class="w-score">
                  <span class="score-value">{{ worker.score }}</span>
                  <span class="score-label">匹配度</span>
                </span>
              </div>
              <div class="w-tags">
                <el-tag 
                  size="small" 
                  v-if="worker.tag" 
                  effect="dark" 
                  :class="[
                    worker.tag === '最优推荐' ? 'tag-best' : '',
                    worker.tag === '高负载' ? 'tag-danger' : '',
                    worker.tag === '执行中' ? 'tag-warning' : '',
                    (!['最优推荐', '高负载', '执行中'].includes(worker.tag)) ? 'tag-green' : ''
                  ]"
                >
                  {{ worker.tag }}
                </el-tag>
                <el-tag size="small" class="tag-hollow" v-for="skill in worker.skills" :key="skill">{{ skill }}</el-tag>
              </div>
              <div class="w-stats">
                <span class="w-stat"><el-icon><Location /></el-icon> {{ worker.distance }} km</span>
                <span class="w-stat"><el-icon><DataLine /></el-icon> {{ worker.carbon }} kg</span>
                <span class="w-stat" :class="{'danger-text': worker.activeTasks > 0}">
                  <el-icon><Briefcase /></el-icon> {{ worker.activeTasks }} 待办
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="assignDialogVisible = false" class="tech-btn-hollow">暂缓下发</el-button>
          <el-button type="primary" @click="confirmAssign" class="tech-btn-solid" :disabled="!assignForm.worker">确认下发工单</el-button>
        </span>
      </template>
    </el-dialog>

    <el-dialog v-model="workOrderDialogVisible" :title="dialogMode === 'execute' ? '现场处置录入' : (dialogMode === 'review' ? '工单闭环验收' : '工单详情')" width="700px" class="tech-dialog" custom-class="tech-dialog">
      <div class="dialog-content-scroll">
        <el-descriptions title="基础信息" :column="2" border class="tech-desc">
          <el-descriptions-item label="工单编号">{{ currentWorkOrder?.id }}</el-descriptions-item>
          <el-descriptions-item label="故障模组">{{ currentWorkOrder?.cellId }}</el-descriptions-item>
          <el-descriptions-item label="当前指派">{{ currentWorkOrder?.assignedWorker }}</el-descriptions-item>
          <el-descriptions-item label="诊断策略">{{ currentWorkOrder?.dispatchStrategy }}</el-descriptions-item>
          <el-descriptions-item label="减碳贡献">
            <span class="carbon-save-text">避免了约 {{ currentWorkOrder?.carbonEmissionKg }} kg CO₂ 排放</span>
          </el-descriptions-item>
        </el-descriptions>

        <div class="divider"></div>
        <div class="panel-subtitle warning-text"><el-icon><WarningFilled /></el-icon> 现场安全与操作规程 (SOP)</div>
        <div class="sop-box">
          <p>{{ safetyAdvice }}</p>
          <el-checkbox-group v-model="workOrderForm.checkedSop" class="sop-checklist" :disabled="dialogMode !== 'execute'">
          <el-checkbox value="step1" class="sop-item">1. 穿戴防电弧服，检查绝缘手套与工具有效性。</el-checkbox>
          <el-checkbox value="step2" class="sop-item">2. 高压断电并挂牌，使用万用表确认无电压残留。</el-checkbox>
          <el-checkbox value="step3" class="sop-item">3. 更换受损模组，扫码绑定新模组SN，并完成BMS握手测试。</el-checkbox>
          </el-checkbox-group>
        </div>

        <div class="divider"></div>
        <el-form label-position="top" class="tech-form">
          <el-form-item label="新备件 SN 码 (扫码录入)">
            <el-input v-model="workOrderForm.newModuleSn" placeholder="请输入或扫描新模组条码" :readonly="dialogMode !== 'execute'">
              <template #prefix><el-icon><Odometer /></el-icon></template>
            </el-input>
          </el-form-item>
         <el-form-item label="现场处置记录">
            <el-input v-model="workOrderForm.notes" type="textarea" :rows="3" placeholder="请详细描述故障现象及处置结果" :readonly="dialogMode !== 'execute'" />
          </el-form-item>
          
          <el-form-item label="现场照片凭证" v-if="dialogMode !== 'execute' && currentWorkOrder?.imageUrls?.length">
            <div class="image-preview-list">
              <el-image
                v-for="(url, index) in currentWorkOrder.imageUrls"
                :key="index"
                :src="url"
                :preview-src-list="currentWorkOrder.imageUrls"
                :initial-index="index"
                fit="cover"
                class="preview-img"
              />
            </div>
          </el-form-item>
          <el-form-item label="现场照片上传 (最多3张)" v-if="dialogMode === 'execute'">
            <el-upload
              action="#"
              list-type="picture-card"
              :auto-upload="false"
              :limit="3"
              :on-change="handleFileChange"
              :on-remove="handleFileRemove"
              :on-exceed="handleExceed"
              class="tech-upload"
            >
              <div class="upload-mock-area" :class="{'is-uploaded': fileList.length > 0}">
                <el-icon class="upload-icon"><Plus /></el-icon>
                <div class="upload-text">拍摄/选择现场照片</div>
                <div class="upload-subtext">更换前/后对比图</div>
              </div>
            </el-upload>
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="workOrderDialogVisible = false" class="tech-btn-hollow">关闭</el-button>
          <el-button v-if="dialogMode === 'execute'" type="primary" @click="submitExecution" class="tech-btn-solid">提交执行记录</el-button>
          <el-button v-if="dialogMode === 'review'" type="success" @click="approveReview" class="tech-btn-solid"><el-icon><SuccessFilled /></el-icon> 确认验收闭环</el-button>
        </span>
      </template>
    </el-dialog>

    <el-dialog v-model="exceptionDialogVisible" title="工单异常挂起" width="500px" class="tech-dialog exception-dialog" custom-class="tech-dialog">
      <div class="exception-warning-banner">
        注意：挂起后工单将暂停执行，并自动流转至电气专家组进行二次评估。
      </div>
      <el-form label-position="top" class="tech-form">
        <el-form-item label="异常原因描述">
          <el-input v-model="exceptionReason" type="textarea" :rows="4" placeholder="例如：现场发现漏液严重，原定更换模组方案无法执行，需整柜隔离..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="exceptionDialogVisible = false" class="tech-btn-hollow">取消</el-button>
          <el-button type="danger" @click="submitException" class="tech-btn-solid danger">确认挂起</el-button>
        </span>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Monitor, Bell, Warning, CircleCheck, DataLine, Location, WarningFilled, UserFilled, Guide, Odometer, Plus, SuccessFilled, Briefcase } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getRecommendedWorkers } from '@/api/index' 

const router = useRouter()

const currentTime = ref('')
const pendingOrders = ref(0)
const processingOrders = ref(0)
const exceptionOrders = ref(0)
const resolvedOrders = ref(0)
const todayOrders = ref(0) 
const urgentOrders = ref(0)

const workOrders = ref([])
const statusFilter = ref('all')
const fileList = ref([])

const recommendedWorkers = ref([])

const loadWorkOrders = () => {
  const localData = localStorage.getItem('workOrders');
  if (localData) {
    workOrders.value = JSON.parse(localData);
  } else {
    workOrders.value = [
      { id: 'WO-MOD-2525', cellId: 'MOD-104 (整组替换)', alertLevel: 3, status: 'Pending', assignedWorker: '未指派', aiConfidence: 0.99, dispatchStrategy: '故障级: 现场换模组', carbonEmissionKg: 0.00, notes: '', newModuleSn: '', sopCompleted: false, location: [121.93, 30.90], locationName: '临港风光储示范基地' },
      { id: 'WO-MOD-8822', cellId: 'MOD-042 (预警干预)', alertLevel: 2, status: 'Processing', assignedWorker: '王师傅', aiConfidence: 0.95, dispatchStrategy: '预警级: 降功率标定', carbonEmissionKg: 0.00, notes: '', newModuleSn: '', sopCompleted: false, location: [121.60, 31.20], locationName: '张江科学城零碳园区' },
      { id: 'WO-MOD-8111', cellId: 'MOD-005 (整组替换)', alertLevel: 3, status: 'Review', assignedWorker: '李师傅', aiConfidence: 0.96, dispatchStrategy: '故障级: 异常超温干预', carbonEmissionKg: 0.05, notes: '旧模组已拔除，新模组接入正常。', newModuleSn: 'SN-LFP-2509A', sopCompleted: true, location: [121.40, 31.17], locationName: '漕河泾综合能源站' },
      { id: 'WO-MOD-6003', cellId: 'MOD-088 (整组替换)', alertLevel: 3, status: 'Resolved', assignedWorker: '张师傅', aiConfidence: 0.98, dispatchStrategy: '故障级: 现场换模组', carbonEmissionKg: 0.25, notes: '已完成整模组拔插替换，BMS握手校准通过。', newModuleSn: 'SN-LFP-2412B', sopCompleted: true, location: [121.93, 30.90], locationName: '临港风光储示范基地' }
    ];
    localStorage.setItem('workOrders', JSON.stringify(workOrders.value));
  }
  updateOrderStats();
}

const updateOrderStats = () => {
  pendingOrders.value = workOrders.value.filter(o => o.status === 'Pending').length;
  processingOrders.value = workOrders.value.filter(o => o.status === 'Processing' || o.status === 'Review').length;
  exceptionOrders.value = workOrders.value.filter(o => o.status === 'Exception').length;
  resolvedOrders.value = workOrders.value.filter(o => o.status === 'Resolved').length;
  urgentOrders.value = workOrders.value.filter(o => o.alertLevel === 3 && (o.status === 'Pending' || o.status === 'Processing')).length;
  todayOrders.value = workOrders.value.length; 
}

const sortedOrders = computed(() => {
  let orders = workOrders.value;
  if (statusFilter.value !== 'all') orders = orders.filter(o => o.status === statusFilter.value);
  return orders.sort((a, b) => {
    const w = { 'Pending': 5, 'Processing': 4, 'Review': 3, 'Exception': 2, 'Resolved': 1 };
    if(w[b.status] !== w[a.status]) return w[b.status] - w[a.status];
    return b.alertLevel - a.alertLevel;
  });
})

const returnToDashboard = () => { router.push('/dashboard') };

const workOrderDialogVisible = ref(false)
const assignDialogVisible = ref(false)
const exceptionDialogVisible = ref(false)

const dialogMode = ref('execute') 
const currentWorkOrder = ref(null)
const exceptionReason = ref('')

const workOrderForm = ref({ notes: '', newModuleSn: '', checkedSop: [] })
const assignForm = ref({ worker: '' })
const miniMapRef = ref(null)
let miniMapChart = null

const safetyAdvice = computed(() => {
  if(!currentWorkOrder.value) return '';
  if(currentWorkOrder.value.alertLevel === 3) {
    return '【系统强制风控】判定为模组级严重故障！必须派发具备高级电工资质的人员执行「停机换模」操作，要求双人同行。';
  }
  return '【常规操作规程】系统判定为模组级预警。请派人前往现场进行深度诊断与重点巡检，暂无需断电。';
})

const getAlertType = (l) => l === 3 ? 'danger' : 'warning';
const getAlertLabel = (l) => l === 3 ? '故障(需换模)' : '预警(需跟踪)';
const getStatusClass = (status) => {
  const map = { 'Pending': 'is-pending', 'Processing': 'is-processing', 'Review': 'is-review', 'Resolved': 'is-resolved', 'Exception': 'is-exception' };
  return map[status] || '';
};
const getStatusText = (status) => {
  const map = { 'Pending': '等待指派', 'Processing': '现场实施中', 'Review': '待管理验收', 'Resolved': '验收已闭环', 'Exception': '异常已挂起' };
  return map[status] || status;
};

const tableRowClassName = ({ row }) => {
  if (row.status === 'Exception') return 'danger-row';
  if (row.status === 'Pending' && row.alertLevel === 3) return 'warning-row';
  return '';
}

const getWorkerSeriesData = () => {
  return recommendedWorkers.value.map(w => {
    const isSelected = assignForm.value.worker === w.name;
    return {
      name: w.name,
      value: w.coord, 
      symbolSize: isSelected ? 40 : 25, 
      itemStyle: {
        color: isSelected ? '#42e695' : '#00f2fe', 
        shadowBlur: isSelected ? 15 : 0,
        shadowColor: '#42e695'
      },
      label: {
        show: true,
        formatter: '{b}',
        position: 'right',
        color: isSelected ? '#42e695' : '#8fa3b7', 
        fontSize: isSelected ? 14 : 12,
        fontWeight: isSelected ? 'bold' : 'normal',
        distance: 8
      },
      z: isSelected ? 100 : 10 
    };
  });
};

const openAssignDialog = async (order) => { 
  currentWorkOrder.value = order; 
  assignForm.value.worker = ''; 
  recommendedWorkers.value = []; 
  
  assignDialogVisible.value = true; 
  
  try {
    const res = await getRecommendedWorkers(order.id);
    let workersList = [];
    if (res.data && Array.isArray(res.data)) {
        workersList = res.data; 
    } else if (res.data && res.data.data && Array.isArray(res.data.data)) {
        workersList = res.data.data; 
    } else if (Array.isArray(res)) {
        workersList = res; 
    }

    const faultLoc = order.location || [121.93, 30.90]; 

    if (workersList.length > 0) {
      recommendedWorkers.value = workersList.map((w) => {
        let parsedCoord = w.coord;
        if (typeof parsedCoord === 'string') {
          parsedCoord = parsedCoord.split(',').map(Number);
        }
        if (!parsedCoord || !Array.isArray(parsedCoord) || parsedCoord.length !== 2) {
          const offsetLng = (Math.random() - 0.5) * 0.04; 
          const offsetLat = (Math.random() - 0.5) * 0.04; 
          parsedCoord = [faultLoc[0] + offsetLng, faultLoc[1] + offsetLat];
        }
        
        // 【防碰撞负载计算】统计此师傅身上背了多少进行中的单子
        const activeTaskCount = workOrders.value.filter(o => 
          o.assignedWorker === w.name && 
          (o.status === 'Processing' || o.status === 'Review')
        ).length;

        let updatedScore = w.score || 85;
        let updatedTag = w.tag || '符合技能';

        if (activeTaskCount > 0) {
          updatedScore = Math.max(60, updatedScore - (activeTaskCount * 15));
          updatedTag = activeTaskCount >= 2 ? '高负载' : '执行中';
        }

        return { 
          ...w, 
          coord: parsedCoord, 
          activeTasks: activeTaskCount,
          score: updatedScore,
          tag: updatedTag
        };
      });
      // 根据算出来的最新分数，重新排序
      recommendedWorkers.value.sort((a, b) => b.score - a.score);
    } else {
      throw new Error("Empty Workers"); 
    }
  } catch (error) {
    const faultLoc = currentWorkOrder.value.location || [121.93, 30.90];
    
    // Fallback Mock 数据增加防碰撞负载计算
    let mockWorkers = [
      { id: 1, name: '张专家', tag: '最优推荐', skills: ['高级电气', '特种高压'], score: 80, distance: 1.9, carbon: 0.42, coord: [faultLoc[0] + 0.015, faultLoc[1] + 0.015] },
      { id: 2, name: '王师傅', tag: '', skills: ['高级电气', 'BMS弱电'], score: 78, distance: 5.8, carbon: 0.29, coord: [faultLoc[0] - 0.02, faultLoc[1] - 0.01] },
      { id: 3, name: '李师傅', tag: '', skills: ['初级运维', '机械维护'], score: 76, distance: 8.0, carbon: 0.4, coord: [faultLoc[0] + 0.01, faultLoc[1] - 0.025] }
    ];

    recommendedWorkers.value = mockWorkers.map(w => {
      const activeTaskCount = workOrders.value.filter(o => 
          o.assignedWorker === w.name && 
          (o.status === 'Processing' || o.status === 'Review')
      ).length;
      
      let updatedScore = w.score;
      let updatedTag = w.tag || '符合技能';
      
      if (activeTaskCount > 0) {
        updatedScore = Math.max(60, updatedScore - (activeTaskCount * 15));
        updatedTag = activeTaskCount >= 2 ? '高负载' : '执行中';
      }
      return { ...w, activeTasks: activeTaskCount, score: updatedScore, tag: updatedTag };
    }).sort((a, b) => b.score - a.score);
  }

  if (recommendedWorkers.value.length > 0) {
    assignForm.value.worker = recommendedWorkers.value[0].name;
  }
  
  nextTick(() => {
    if(miniMapChart) updateMapData();
  });
}

const updateMapData = () => {
  if(!miniMapChart) return;
  // 修复 ECharts 缺少 type 导致的 Unknown series 报错
  miniMapChart.setOption({
    series: [
      { name: '故障点', type: 'effectScatter', coordinateSystem: 'geo' }, 
      { name: '运维人员', type: 'scatter', coordinateSystem: 'geo', data: getWorkerSeriesData() }
    ]
  });
}

const selectWorker = (worker) => {
  assignForm.value.worker = worker.name;
  updateMapData();
}

const confirmAssign = () => { 
  currentWorkOrder.value.assignedWorker = assignForm.value.worker; 
  currentWorkOrder.value.status = 'Processing'; 
  
  const selectedW = recommendedWorkers.value.find(w => w.name === assignForm.value.worker);
  if(selectedW) {
    currentWorkOrder.value.carbonEmissionKg = selectedW.carbon;
  }

  saveAndRefresh('智能派单成功，现场工程师已收到任务！');
  assignDialogVisible.value = false; 
}

const openExecuteDialog = (order) => {
  currentWorkOrder.value = order;
  dialogMode.value = 'execute';
  workOrderForm.value = { notes: '', newModuleSn: '', checkedSop: [] };
  fileList.value = [];
  workOrderDialogVisible.value = true;
}

// 👇 新增：将文件转为 Base64 格式的工具函数
// 👇 新增：自带高压缩比的图片处理函数，防止撑爆 localStorage
const getBase64 = (file) => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = (event) => {
      const img = new Image();
      img.src = event.target.result;
      img.onload = () => {
        // 创建 Canvas 进行物理压缩
        const canvas = document.createElement('canvas');
        // 强制把图片宽度压缩到 400 像素（足够工单缩略图看清了）
        const MAX_WIDTH = 400;
        const scaleSize = MAX_WIDTH / img.width;
        canvas.width = MAX_WIDTH;
        canvas.height = img.height * scaleSize;
        
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        
        // 压缩成 JPEG 格式，画质降低到 0.6，几 MB 的图瞬间变成几十 KB
        const compressedBase64 = canvas.toDataURL('image/jpeg', 0.6);
        resolve(compressedBase64);
      };
    };
    reader.onerror = error => reject(error);
  });
}

// 修改后的提交函数
const submitExecution = async () => {
  if (workOrderForm.value.checkedSop.length < 3) return ElMessage.warning('请先勾选确认所有的 SOP 步骤');
  if (!workOrderForm.value.newModuleSn) return ElMessage.warning('请扫描或输入新替换模组的 SN 码');
  if (!workOrderForm.value.notes) return ElMessage.warning('请填写现场处置结论');
  
  // 👇 新增：处理图片，将 fileList 里的图片转换为 Base64 存入工单
  const base64Images = [];
  for (let i = 0; i < fileList.value.length; i++) {
    if (fileList.value[i].raw) {
      const base64 = await getBase64(fileList.value[i].raw);
      base64Images.push(base64);
    }
  }
  currentWorkOrder.value.imageUrls = base64Images;
  // 👆 新增结束

  currentWorkOrder.value.status = 'Review'; 
  currentWorkOrder.value.notes = workOrderForm.value.notes;
  currentWorkOrder.value.newModuleSn = workOrderForm.value.newModuleSn;
  currentWorkOrder.value.sopCompleted = true;
  saveAndRefresh('现场记录已提交，等待后台管理员审核验收。');
  workOrderDialogVisible.value = false;
}

const openReviewDialog = (order) => {
  currentWorkOrder.value = order;
  dialogMode.value = 'review';
  workOrderForm.value.notes = order.notes;
  workOrderForm.value.newModuleSn = order.newModuleSn;
  workOrderDialogVisible.value = true;
}

const approveReview = () => {
  currentWorkOrder.value.status = 'Resolved';
  saveAndRefresh('工单审核通过，新旧备件流水已自动记账并归档。');
  workOrderDialogVisible.value = false;
}

const viewWorkOrderDetails = (order) => {
  currentWorkOrder.value = order;
  dialogMode.value = 'view';
  workOrderForm.value.notes = order.notes;
  workOrderForm.value.newModuleSn = order.newModuleSn;
  workOrderDialogVisible.value = true;
}

const openExceptionDialog = (order) => {
  currentWorkOrder.value = order;
  exceptionReason.value = '';
  exceptionDialogVisible.value = true;
}

const submitException = () => {
  if (!exceptionReason.value) return ElMessage.warning('请输入异常描述');
  currentWorkOrder.value.status = 'Exception';
  currentWorkOrder.value.notes = `【异常报告】：${exceptionReason.value}`;
  saveAndRefresh('异常已触发挂起，已自动推送给电气专家组！');
  exceptionDialogVisible.value = false;
}

const saveAndRefresh = (msg) => {
  localStorage.setItem('workOrders', JSON.stringify(workOrders.value));
  updateOrderStats();
  if (msg) ElMessage.success({ message: msg, customClass: 'tech-message' });
}

const handleFileChange = (uploadFile, uploadFiles) => { fileList.value = uploadFiles; }
const handleFileRemove = (uploadFile, uploadFiles) => { fileList.value = uploadFiles; }
const handleExceed = () => { ElMessage.warning('最多只能上传 3 张现场照片凭证'); }

const updateCurrentTime = () => {
  const now = new Date();
  currentTime.value = now.toLocaleString('zh-CN', { hour12: false });
}

const initMiniMap = async () => {
  if (!miniMapRef.value) return;
  if (miniMapChart) miniMapChart.dispose();
  miniMapChart = echarts.init(miniMapRef.value);

  try {
    const response = await fetch('/shanghai.json').catch(() => fetch('/data/shanghai.json'));
    const geoJson = await response.json();
    echarts.registerMap('shanghai', geoJson);
  } catch(e) { console.error("微观地图加载失败", e) }

  const faultLocation = currentWorkOrder.value?.location || [121.93, 30.90];

  const option = {
    geo: {
      map: 'shanghai', center: faultLocation, zoom: 8, roam: true,
      itemStyle: { areaColor: '#0a101f', borderColor: '#00f2fe', borderWidth: 1.5 },
      emphasis: { itemStyle: { areaColor: '#162442' }, label: { show: false } },
      zlevel: 0
    },
    series: [
      {
        name: '故障点', type: 'effectScatter', coordinateSystem: 'geo', symbolSize: 20,
        itemStyle: { color: '#ff0844', shadowBlur: 20, shadowColor: '#ff0844' },
        zlevel: 1,
        data: [{ name: currentWorkOrder.value?.cellId, value: faultLocation }]
      },
      {
        name: '运维人员', type: 'scatter', coordinateSystem: 'geo', symbol: 'pin',
        zlevel: 2,
        data: [] 
      }
    ]
  };

  miniMapChart.setOption(option);
  
  miniMapChart.on('click', (params) => {
    if(params.seriesName === '运维人员') {
      const targetWorker = recommendedWorkers.value.find(w => w.name === params.name);
      if(targetWorker) selectWorker(targetWorker);
    }
  });

  updateMapData();
}

onMounted(() => {
  loadWorkOrders(); 
  updateCurrentTime(); 
  setInterval(updateCurrentTime, 1000);
})
</script>

<style scoped>
/* =========================================================
   组件级布局和背景样式
   ========================================================= */
.work-order-wrapper {
  position: relative;
  width: 100%;
  min-height: calc(100vh - 60px);
  padding: 20px;
  box-sizing: border-box;
  color: #fff;
  font-family: 'PingFang SC', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  overflow: hidden;
  background: #04070e;
  background-image: 
    radial-gradient(circle at 50% 0%, rgba(0, 242, 254, 0.08) 0%, transparent 60%), 
    linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px), 
    linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
  background-size: 100% 100%, 30px 30px, 30px 30px;
}

.tech-watermark {
  position: absolute;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
  color: rgba(255, 255, 255, 0.05);
  font-size: 14px;
  font-weight: bold;
  letter-spacing: 4px;
  pointer-events: none;
  z-index: 100;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  position: relative;
  z-index: 1;
}

.header-left { display: flex; align-items: center; gap: 15px; }

.tech-title { 
  font-size: 22px; 
  font-weight: bold; 
  background: linear-gradient(90deg, #00f2fe 0%, #4facfe 100%); 
  -webkit-background-clip: text; 
  color: transparent; 
  letter-spacing: 1px;
}

.live-tag { 
  position: relative; 
  padding-left: 20px; 
  border: 1px solid #00f2fe !important; 
  background: rgba(0, 242, 254, 0.1) !important; 
  color: #00f2fe !important;
}
.live-dot { 
  position: absolute; 
  left: 8px; 
  top: 50%; 
  transform: translateY(-50%); 
  width: 6px; 
  height: 6px; 
  background-color: #00f2fe; 
  border-radius: 50%; 
  box-shadow: 0 0 8px #00f2fe; 
  animation: pulse-dot 1.5s infinite; 
}
@keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.2; } }

.header-right { display: flex; align-items: center; gap: 20px; }
.time-display { font-family: 'Courier New', Courier, monospace; color: #4facfe; font-size: 16px; font-weight: bold;}
.tech-btn-back { background: rgba(0, 242, 254, 0.05); border: 1px solid rgba(0, 242, 254, 0.3); color: #00f2fe; }
.tech-btn-back:hover { background: rgba(0, 242, 254, 0.2); box-shadow: 0 0 15px rgba(0, 242, 254, 0.5); color: #fff;}

.main-content-grid { display: flex; flex-direction: column; gap: 20px; position: relative; z-index: 1;}
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }

.stat-card {
  position: relative; 
  background: linear-gradient(180deg, rgba(16, 22, 36, 0.8) 0%, rgba(10, 14, 25, 0.9) 100%); 
  border: 1px solid rgba(0, 242, 254, 0.2); 
  box-shadow: 0 0 15px rgba(0, 0, 0, 0.5), inset 0 0 15px rgba(0, 242, 254, 0.05); 
  border-radius: 4px; 
  padding: 15px 20px; 
  display: flex; 
  align-items: center; 
  gap: 15px;
  overflow: hidden; 
}

.card-corner { position: absolute; width: 10px; height: 10px; border: 2px solid transparent; z-index: 10; }
.card-corner.top-left { top: -1px; left: -1px; border-top-color: #00f2fe; border-left-color: #00f2fe; }
.card-corner.bottom-right { bottom: -1px; right: -1px; border-bottom-color: #00f2fe; border-right-color: #00f2fe; }

.stat-icon { width: 50px; height: 50px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 24px;}
.stat-icon.warning { background: rgba(246, 211, 101, 0.1); color: #f6d365; border: 1px solid rgba(246, 211, 101, 0.3);}
.stat-icon.processing { background: rgba(0, 242, 254, 0.1); color: #00f2fe; border: 1px solid rgba(0, 242, 254, 0.3);}
.stat-icon.danger { background: rgba(255, 8, 68, 0.1); color: #ff0844; border: 1px solid rgba(255, 8, 68, 0.3);}
.stat-icon.success { background: rgba(66, 230, 149, 0.1); color: #42e695; border: 1px solid rgba(66, 230, 149, 0.3);}

.stat-info { display: flex; flex-direction: column; }
.stat-value { font-size: 28px; font-weight: 900; font-family: 'Arial', sans-serif; margin-bottom: 2px;}
.stat-label { font-size: 13px; color: #8fa3b7; font-weight: bold;}

.glow-yellow { color: #f6d365; }
.glow-blue { color: #00f2fe; }
.glow-red { color: #ff0844; }
.glow-green { color: #42e695; }

.data-table-container { height: calc(100vh - 210px); display: flex; flex-direction: column; padding: 20px;}

.tech-box { 
  background: rgba(11, 18, 32, 0.7); 
  border: 1px solid #1c2e42; 
  border-radius: 4px; 
}

.table-header-ops { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }

:deep(.tech-radio-group .el-radio-button__inner) { background: transparent; border: 1px solid #1c2e42 !important; color: #8fa3b7;}
:deep(.tech-radio-group .el-radio-button__original-radio:checked + .el-radio-button__inner) { background: rgba(0, 242, 254, 0.1); border-color: #00f2fe !important; color: #00f2fe;}

:deep(.tech-table) { 
  background-color: transparent !important; 
  --el-table-bg-color: transparent !important; 
  --el-table-tr-bg-color: transparent !important; 
  --el-table-header-bg-color: rgba(0, 242, 254, 0.05) !important; 
  --el-table-row-hover-bg-color: rgba(0, 242, 254, 0.1) !important; 
  --el-table-border-color: #1c2e42 !important; 
  --el-table-text-color: #fff !important; 
}
:deep(.tech-table th.el-table__cell) { background-color: var(--el-table-header-bg-color) !important; border-bottom: 1px solid #1c2e42 !important; color: #8fa3b7; padding: 12px 0;}
:deep(.tech-table tr), :deep(.tech-table td.el-table__cell) { border-bottom: 1px solid #1c2e42 !important; padding: 12px 0;}
:deep(.tech-table::before) { display: none; }

.order-id { font-family: 'Courier New', Courier, monospace; color: #fff; }
.cell-id-link { color: #00f2fe; cursor: pointer; display: flex; align-items: center; gap: 5px;}
.level-tag { border: none; font-weight: normal;}
.strategy-col { display: flex; align-items: center; justify-content: space-between; padding-right: 15px;}
.strategy-text { color: #fff; font-size: 13px;}
.confidence { font-family: 'Courier New', Courier, monospace; font-size: 12px; color: #8fa3b7; }
.confidence.high { color: #42e695; }

/* 员工名字与占位符 */
.worker-name { display: flex; align-items: center; justify-content: center; gap: 5px; color: #fff;}
.empty-placeholder { color: #5a6d81; font-weight: bold; letter-spacing: 2px; }

.status-indicator { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 12px; font-size: 12px;}
.status-dot { width: 6px; height: 6px; border-radius: 50%; }
.is-pending { color: #f6d365; } .is-pending .status-dot { background: #f6d365; }
.is-processing { color: #00f2fe; } .is-processing .status-dot { background: #00f2fe; }
.is-review { color: #a872ff; } .is-review .status-dot { background: #a872ff; }
.is-resolved { color: #42e695; } .is-resolved .status-dot { background: #42e695; }
.is-exception { color: #ff0844; } .is-exception .status-dot { background: #ff0844; }

/* 在 style 标签底部加上这段 */
.image-preview-list {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.preview-img {
  width: 90px;
  height: 90px;
  border-radius: 6px;
  border: 1px solid #1c2e42;
  cursor: zoom-in;
}

</style>

<style>
/* =========================================================
   全局非作用域样式（UNSCOPED）：彻底解决弹窗内部组件白底
   由于 Element Plus 的 el-dialog 渲染在 body 层，
   必须在这里用全局强穿透解决所有样式问题
   ========================================================= */

/* 遮罩层 */
.el-overlay {
  background-color: rgba(0, 0, 0, 0.7) !important;
  backdrop-filter: blur(2px);
}

/* 弹窗主体 */
.tech-dialog {
  background: #0b1220 !important;
  border: 1px solid #1a293d !important;
  border-radius: 8px !important;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.8) !important;
}

/* 弹窗标题栏 */
.tech-dialog .el-dialog__header {
  border-bottom: 1px solid #1c2e42 !important;
  margin-right: 0 !important;
  padding: 15px 20px !important;
}
.tech-dialog .el-dialog__title {
  font-size: 16px !important;
  font-weight: bold !important;
  color: #00f2fe !important;
}
.tech-dialog .el-dialog__headerbtn .el-dialog__close { color: #5a6d81 !important; }
.tech-dialog .el-dialog__headerbtn:hover .el-dialog__close { color: #00f2fe !important; }

/* 弹窗内容区 */
.tech-dialog .el-dialog__body {
  color: #fff !important;
  padding: 20px !important;
}
.tech-dialog .el-dialog__footer {
  padding: 15px 20px !important;
  text-align: right !important;
  border-top: 1px solid #1c2e42 !important;
}

/* ================= 派单中枢特有样式 ================= */
.tech-dialog .assign-task-header {
  background: #111a28 !important;
  border: 1px solid #1c2e42 !important;
  border-radius: 4px !important;
  padding: 10px 15px !important;
  margin-bottom: 10px !important;
}
.tech-dialog .task-node-info { display: flex; align-items: center; color: #00f2fe; font-size: 14px; }
.tech-dialog .task-text { margin: 0 15px 0 8px; font-weight: bold; }
.tech-dialog .task-badge { background: #c54a5c; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; }

.tech-dialog .assign-warning-banner,
.tech-dialog .exception-warning-banner {
  background: rgba(197, 74, 92, 0.15) !important;
  border-left: 4px solid #c54a5c !important;
  color: #c54a5c !important;
  padding: 10px 15px !important;
  font-size: 13px !important;
  display: flex !important;
  align-items: center !important;
  gap: 8px !important;
  margin-bottom: 15px !important;
}

.tech-dialog .assign-container { display: flex; height: 400px; gap: 15px;}
.tech-dialog .assign-left { flex: 1; display: flex; flex-direction: column;}
.tech-dialog .assign-right { width: 380px; display: flex; flex-direction: column;}
.tech-dialog .panel-subtitle { font-size: 13px; color: #8fa3b7; margin-bottom: 10px; display: flex; align-items: center;}
.tech-dialog .panel-subtitle::before { content: ''; display: inline-block; width: 3px; height: 12px; background: #00f2fe; margin-right: 8px;}
.tech-dialog .map-box { flex: 1; background: #090e17; border-radius: 4px; border: 1px solid #1c2e42; position: relative; }

.tech-dialog .recommendation-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; padding-right: 5px;}
.tech-dialog .recommendation-list::-webkit-scrollbar { width: 4px; }
.tech-dialog .recommendation-list::-webkit-scrollbar-thumb { background: #1c2e42; border-radius: 4px; }

.tech-dialog .worker-card { 
  background: #111a28 !important; 
  border: 1px solid #1c2e42 !important; 
  border-radius: 6px; 
  padding: 15px; 
  cursor: pointer; 
  transition: all 0.2s;
}
.tech-dialog .worker-card:hover { border-color: #32597a !important; }

.tech-dialog .worker-card.is-selected { 
  background: rgba(0, 242, 254, 0.08) !important; 
  border: 1px solid #00f2fe !important; 
  box-shadow: 0 0 15px rgba(0, 242, 254, 0.15) inset !important;
}
.tech-dialog .worker-card.is-selected .w-name { color: #00f2fe !important; text-shadow: 0 0 8px rgba(0, 242, 254, 0.4) !important;}
.tech-dialog .worker-card.is-selected .score-value { color: #00f2fe !important;}
.tech-dialog .worker-card.is-selected .score-label,
.tech-dialog .worker-card.is-selected .w-stat { color: #8fa3b7 !important; }
.tech-dialog .worker-card.is-selected .tag-hollow { color: #00f2fe !important; border-color: rgba(0, 242, 254, 0.5) !important; background: transparent !important;}

.tech-dialog .worker-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;}
.tech-dialog .avatar-icon { font-size: 18px; color: #00f2fe; background: rgba(0, 242, 254, 0.1); padding: 5px; border-radius: 50%; margin-right: 5px;}
.tech-dialog .w-name { color: #fff; font-size: 16px; font-weight: bold; display: flex; align-items: center;}
.tech-dialog .w-score { text-align: right; line-height: 1; }
.tech-dialog .score-value { display: block; color: #fff; font-size: 22px; font-weight: normal;}
.tech-dialog .score-label { color: #5a6d81; font-size: 12px;}
.tech-dialog .w-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px;}
.tech-dialog .w-tags .el-tag { border: none; border-radius: 2px;}

/* 动态标签色彩防碰撞警示 */
.tech-dialog .tag-best, .tech-dialog .tag-green { background: #234836 !important; color: #42e695 !important;}
.tech-dialog .tag-danger { background: rgba(197, 74, 92, 0.2) !important; color: #c54a5c !important;}
.tech-dialog .tag-warning { background: rgba(246, 211, 101, 0.2) !important; color: #f6d365 !important;}
.tech-dialog .tag-hollow { background: transparent !important; border: 1px solid #2a3c52 !important; color: #8fa3b7 !important;}
.tech-dialog .w-stats { display: flex; gap: 15px; font-size: 12px; color: #5a6d81;}
.tech-dialog .w-stat { display: flex; align-items: center; gap: 4px;}
.tech-dialog .danger-text { color: #f6d365 !important; font-weight: bold;}

/* ================= 工单详情与现场录入特有样式 ================= */
.tech-dialog .dialog-content-scroll { padding: 0; max-height: 60vh; overflow-y: auto; }
.tech-dialog .carbon-save-text { color: #42e695 !important; font-weight: bold;}
.tech-dialog .divider { height: 1px; background: #1c2e42; margin: 20px 0; }
.tech-dialog .warning-text { color: #f6d365 !important;}

/* 极致修复 el-descriptions 描述列表的白底与边框 */
.tech-dialog .tech-desc .el-descriptions__body { background-color: transparent !important; }
.tech-dialog .tech-desc table,
.tech-dialog .tech-desc tbody,
.tech-dialog .tech-desc tr,
.tech-dialog .tech-desc th,
.tech-dialog .tech-desc td {
  border-color: #1c2e42 !important;
  background-color: transparent !important;
}
.tech-dialog .tech-desc .el-descriptions__label.is-bordered-label {
  background-color: rgba(0, 242, 254, 0.05) !important;
  color: #8fa3b7 !important;
  border-color: #1c2e42 !important;
}
.tech-dialog .tech-desc .el-descriptions__content.is-bordered-content {
  background-color: #0b1220 !important;
  color: #fff !important;
  border-color: #1c2e42 !important;
}

/* SOP提示框 */
.tech-dialog .sop-box {
  background: rgba(246, 211, 101, 0.05) !important;
  border: 1px solid #3d3519 !important;
  border-radius: 4px !important;
  padding: 15px !important;
  color: #e2e8f0 !important;
  font-size: 13px !important;
  line-height: 1.6 !important;
}
.tech-dialog .sop-checklist { display: flex; flex-direction: column; gap: 10px; margin-top: 15px;}
.tech-dialog .sop-item { margin-right: 0;}

/* 彻底修复所有输入框、文本域、复选框的亮色白底问题 */
.tech-dialog .el-form-item__label { color: #8fa3b7 !important; }

/* Input & Textarea 修复 */
.tech-dialog .el-input__wrapper,
.tech-dialog .el-textarea__inner {
  background-color: #090e17 !important;
  box-shadow: 0 0 0 1px #1c2e42 inset !important;
  color: #fff !important;
}
.tech-dialog .el-input__inner { color: #fff !important; }
.tech-dialog .el-input__inner::placeholder,
.tech-dialog .el-textarea__inner::placeholder { color: #5a6d81 !important; }

/* Focus 状态 */
.tech-dialog .el-input__wrapper.is-focus,
.tech-dialog .el-textarea__inner:focus {
  box-shadow: 0 0 0 1px #00f2fe inset !important;
}

/* 禁用/只读状态 */
.tech-dialog .el-input.is-disabled .el-input__wrapper,
.tech-dialog .el-textarea.is-disabled .el-textarea__inner {
  background-color: rgba(11, 18, 32, 0.5) !important;
  color: #5a6d81 !important;
}

/* Checkbox 修复 */
.tech-dialog .el-checkbox__label { color: #8fa3b7 !important; }
.tech-dialog .el-checkbox__input.is-checked + .el-checkbox__label { color: #00f2fe !important; }
.tech-dialog .el-checkbox__inner {
  background-color: #090e17 !important;
  border-color: #1c2e42 !important;
}
.tech-dialog .el-checkbox__input.is-checked .el-checkbox__inner {
  background-color: #00f2fe !important;
  border-color: #00f2fe !important;
}
.tech-dialog .el-checkbox__input.is-disabled .el-checkbox__inner {
  background-color: rgba(11, 18, 32, 0.5) !important;
}

/* Upload 图片上传区域修复 */
.tech-dialog .el-upload--picture-card {
  background-color: #090e17 !important;
  border: 1px dashed #1c2e42 !important;
  border-radius: 6px !important;
}
.tech-dialog .el-upload--picture-card:hover {
  border-color: #00f2fe !important;
  color: #00f2fe !important;
}

/* 底部操作按钮修复 */
.tech-dialog .tech-btn-hollow {
  background: transparent !important;
  border: 1px solid #2a3c52 !important;
  color: #8fa3b7 !important;
  border-radius: 4px !important;
}
.tech-dialog .tech-btn-hollow:hover {
  border-color: #5a6d81 !important;
  color: #fff !important;
}
.tech-dialog .tech-btn-solid {
  background: #00f2fe !important;
  border: none !important;
  color: #000 !important;
  font-weight: bold !important;
  border-radius: 4px !important;
}
.tech-dialog .tech-btn-solid:hover { background: #4facfe !important; }
.tech-dialog .tech-btn-solid:disabled { background: #1c2e42 !important; color: #5a6d81 !important; }
.tech-dialog .tech-btn-solid.danger { background: #c54a5c !important; color: #fff !important; }
.tech-dialog .tech-btn-solid.danger:hover { background: #e65b70 !important; }

/* =========================================================
   全局 Message 提示框：暗黑科技风深度定制
   注意：由于 Message 渲染在最外层，必须写在这里
   ========================================================= */
.el-message.tech-message {
  background: rgba(11, 18, 32, 0.9) !important; /* 深蓝色半透明底 */
  border: 1px solid #00f2fe !important; /* 赛博蓝边框 */
  box-shadow: 0 0 20px rgba(0, 242, 254, 0.2) !important; /* 柔和的发光 */
  border-radius: 8px !important;
  color: #fff !important;
  padding: 15px 20px !important;
  display: flex !important;
  align-items: center !important;
}

/* 成功状态图标颜色重写 */
.el-message.tech-message .el-message__icon {
  color: #42e695 !important; /* 荧光绿 */
  font-size: 18px !important;
  margin-right: 10px !important;
}

/* 提示文字颜色 */
.el-message.tech-message .el-message__content {
  color: #fff !important;
  font-weight: bold !important;
  letter-spacing: 1px !important;
}

/* 确保提示框层级最高，不会被地图或其他遮罩挡住 */
.el-message {
  z-index: 99999 !important; 
}
</style>