<template>
  <div class="train-platform">
    <el-card class="card-container">
      <template #header>
        <div class="card-header">
          <span>算法训练平台</span>
        </div>
      </template>
      
      <el-row :gutter="20">
        <el-col :span="24">
          <el-card shadow="hover" class="platform-section-card">
            <template #header>
              <div class="section-header algorithm-selection-header">
                <div class="header-title">
                  <el-icon class="header-icon"><Setting /></el-icon>
                  <span>算法模型选择</span>
                </div>
              </div>
            </template>
            <div class="section-content">
            <el-form label-position="top" class="section-form horizontal-form">
              <el-form-item label="选择算法模型" class="algorithm-model-item">
                <el-radio-group v-model="selectedAlgorithm" @change="onAlgorithmChange" class="algorithm-radio-group horizontal-radio-group">
                  <el-radio value="baseline">Baseline（传统机器学习）</el-radio>
                  <el-radio value="bilstm">BiLSTM（双向长短期记忆网络）</el-radio>
                  <el-radio value="deepphm">DeepHPM（深度物理信息神经网络）</el-radio>
                </el-radio-group>
              </el-form-item>
            </el-form>
            
            <el-row :gutter="20" class="params-row">
              <el-col :span="8">
                <div class="param-section">
                  <el-divider content-position="left" class="section-divider">
                    <span class="divider-text">
                      <el-icon><Connection /></el-icon>
                      网络结构参数
                    </span>
                  </el-divider>
                  <el-form label-position="top" class="param-form">
                    <el-form-item label="层数">
                      <el-input-number 
                        v-model="networkParams.layers" 
                        :min="1" 
                        :max="10" 
                        :step="1"
                        style="width: 100%"
                      />
                    </el-form-item>
                    <el-form-item label="节点数">
                      <el-input-number 
                        v-model="networkParams.nodes" 
                        :min="1" 
                        :max="1000" 
                        :step="10"
                        style="width: 100%"
                      />
                    </el-form-item>
                    <el-form-item label="激活函数">
                      <el-select v-model="networkParams.activation" placeholder="请选择激活函数" style="width: 100%">
                        <el-option label="Tanh" value="tanh"></el-option>
                        <el-option label="ReLU" value="relu"></el-option>
                        <el-option label="Sigmoid" value="sigmoid"></el-option>
                        <el-option label="Sin" value="sin"></el-option>
                      </el-select>
                    </el-form-item>
                    <div class="param-placeholder"></div>
                  </el-form>
                </div>
              </el-col>
              
              <el-col :span="8">
                <div class="param-section">
                  <el-divider content-position="left" class="section-divider">
                    <span class="divider-text">
                      <el-icon><Tools /></el-icon>
                      训练超参数
                    </span>
                  </el-divider>
                  <el-form label-position="top" class="param-form">
                    <el-form-item label="学习率">
                      <el-input-number 
                        v-model="hyperParams.learningRate" 
                        :min="0.0001" 
                        :max="0.1" 
                        :step="0.001"
                        :precision="4"
                        style="width: 100%"
                      />
                    </el-form-item>
                    <el-form-item label="批大小">
                      <el-input-number 
                        v-model="hyperParams.batchSize" 
                        :min="1" 
                        :max="1024" 
                        :step="1"
                        style="width: 100%"
                      />
                    </el-form-item>
                    <el-form-item label="迭代次数">
                      <el-input-number 
                        v-model="hyperParams.epochs" 
                        :min="1" 
                        :max="10000" 
                        :step="10"
                        style="width: 100%"
                      />
                    </el-form-item>
                    <div class="param-placeholder"></div>
                  </el-form>
                </div>
              </el-col>
              
              <el-col :span="8">
                <div class="param-section">
                  <el-divider content-position="left" class="section-divider">
                    <span class="divider-text">
                      <el-icon><Operation /></el-icon>
                      优化器选择
                    </span>
                  </el-divider>
                  <el-form label-position="top" class="param-form">
                    <el-form-item label="优化器">
                      <el-select v-model="hyperParams.optimizer" placeholder="请选择优化器" style="width: 100%">
                        <el-option label="Adam" value="adam"></el-option>
                        <el-option label="SGD" value="sgd"></el-option>
                        <el-option label="RMSprop" value="rmsprop"></el-option>
                      </el-select>
                    </el-form-item>
                    <div class="param-placeholder"></div>
                    <div class="param-placeholder"></div>
                    <div class="param-placeholder"></div>
                  </el-form>
                </div>
              </el-col>
            </el-row>
            </div>
          </el-card>
        </el-col>
      </el-row>
      
      <el-row :gutter="20" style="margin-top: 20px;">
        <el-col :span="12">
          <el-card shadow="hover" class="platform-section-card">
            <template #header>
              <div class="section-header training-control-header">
                <div class="header-title">
                  <el-icon class="header-icon"><VideoPlay /></el-icon>
                  <span>训练控制</span>
                </div>
              </div>
            </template>
            <div class="section-content">
            <el-form label-position="top" class="section-form training-control-form">
              <el-form-item label="数据集划分" class="dataset-split-item">
                <div class="dataset-split-container">
                  <el-slider
                    v-model="datasetSplit.trainRatio"
                    :min="0.5"
                    :max="0.9"
                    :step="0.05"
                    show-input
                    :format-tooltip="formatTooltip"
                    class="dataset-split-slider"
                  />
                  <div class="dataset-split-tags">
                    <div class="split-tag-item">
                      <el-icon class="tag-icon"><DataAnalysis /></el-icon>
                      <span class="tag-label">训练集</span>
                      <el-tag type="success" size="small" class="split-tag">{{ Math.round(datasetSplit.trainRatio * 100) }}%</el-tag>
                    </div>
                    <div class="split-tag-item">
                      <el-icon class="tag-icon"><DocumentChecked /></el-icon>
                      <span class="tag-label">验证集</span>
                      <el-tag type="warning" size="small" class="split-tag">{{ Math.round((1-datasetSplit.trainRatio) * 100) }}%</el-tag>
                    </div>
                  </div>
                </div>
              </el-form-item>
              
              <el-form-item label="电芯选择" class="battery-selection-form-item">
                <div class="battery-selection-wrapper">
                  <div class="left-panel-filter-section">
                    <div class="filter-section-header">
                      <el-icon class="section-icon"><FolderOpened /></el-icon>
                      <span class="section-title">可选电芯筛选</span>
                    </div>
                    <div class="battery-type-filter">
                      <div class="filter-row">
                        <span class="filter-label">
                          <el-icon><Filter /></el-icon>
                          按类型筛选：
                        </span>
                        <el-radio-group v-model="selectedDatasetType" size="small" @change="filterBatteriesByType">
                          <el-radio-button :value="''">全部</el-radio-button>
                          <el-radio-button value="train">训练集 (Train)</el-radio-button>
                          <el-radio-button value="validation">验证集 (Validation)</el-radio-button>
                          <el-radio-button value="test">测试集 (Test)</el-radio-button>
                        </el-radio-group>
                      </div>
                      <div class="type-counts-row">
                        <span class="count-label">数量统计：</span>
                        <div class="count-items">
                          <span class="count-item">训练: {{ typeCounts.train }}</span>
                          <span class="count-item">验证: {{ typeCounts.validation }}</span>
                          <span class="count-item">测试: {{ typeCounts.test }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  <el-transfer
                    :key="`transfer-${selectedDatasetType}-${filteredCellOptions.length}`"
                    v-model="selectedCells"
                    filterable
                    :filter-method="filterMethod"
                    :titles="['可选电芯 (' + filteredCellOptions.length + ')', '已选电芯 (' + selectedCells.length + ')']"
                    :format="{
                      noChecked: '${total}',
                      hasChecked: '${checked}/${total}'
                    }"
                    :data="filteredCellOptions"
                    :pagination="false"
                    class="battery-transfer">
                  </el-transfer>
                </div>
              </el-form-item>
            </el-form>
            
            <div class="cell-selection-actions">
              <el-button 
                type="primary" 
                plain
                @click="selectAllAvailable"
                :disabled="availableCellsCount === 0"
                class="selection-btn">
                <el-icon><CircleCheck /></el-icon>
                <span>全选可用电池</span>
              </el-button>
              <el-button 
                @click="clearSelected"
                :disabled="selectedCells.length === 0"
                class="selection-btn">
                <el-icon><Delete /></el-icon>
                <span>清空已选</span>
              </el-button>
            </div>
            
            <div class="training-actions">
              <el-button 
                type="primary" 
                size="large" 
                :disabled="isTraining" 
                @click="startTraining"
                :loading="isTraining"
                class="start-training-btn"
              >
                <el-icon v-if="!isTraining" class="btn-icon"><VideoPlay /></el-icon>
                <span class="btn-text">{{ isTraining ? '训练中...' : '开始训练' }}</span>
              </el-button>
              <el-button 
                size="large" 
                :disabled="!isTraining" 
                @click="stopTraining"
                class="stop-training-btn"
              >
                <el-icon class="btn-icon"><VideoPause /></el-icon>
                <span class="btn-text">停止训练</span>
              </el-button>
            </div>
            
            <el-divider content-position="left" class="progress-divider" style="margin: 15px 0 12px 0;">
              <span class="divider-text">
                <el-icon><TrendCharts /></el-icon>
                训练进度
              </span>
            </el-divider>
            <div v-if="isTraining" class="training-progress">
              <div class="progress-header">
                <div class="progress-info">
                  <el-icon class="progress-icon"><Clock /></el-icon>
                  <span class="progress-text">当前轮次: <strong>{{ currentEpoch }}</strong> / {{ hyperParams.epochs }}</span>
                </div>
                <div class="progress-percentage-wrapper">
                  <span class="progress-percentage">{{ progressPercentage }}%</span>
                </div>
              </div>
              <el-progress 
                :percentage="progressPercentage" 
                :status="trainingStatus"
                :stroke-width="18"
                class="training-progress-bar"
                :show-text="false"
              />
              <div class="metrics-display">
                <div class="metric-card-item">
                  <div class="metric-header-item">
                    <el-icon class="metric-icon train-icon"><TrendCharts /></el-icon>
                    <span class="metric-label">训练损失</span>
                  </div>
                  <span class="metric-value train-value">{{ currentMetrics.trainLoss.toFixed(6) }}</span>
                </div>
                <div class="metric-card-item">
                  <div class="metric-header-item">
                    <el-icon class="metric-icon val-icon"><DataAnalysis /></el-icon>
                    <span class="metric-label">验证损失</span>
                  </div>
                  <span class="metric-value val-value">{{ currentMetrics.valLoss.toFixed(6) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="training-placeholder">
              <el-empty description="点击开始训练按钮启动训练任务" :image-size="100">
                <template #image>
                  <el-icon style="font-size: 100px; color: #c0c4cc;"><VideoPlay /></el-icon>
                </template>
              </el-empty>
            </div>
            </div>
          </el-card>
        </el-col>
        
        <el-col :span="12">
          <el-card shadow="hover" class="platform-section-card monitoring-evaluation-card">
            <template #header>
              <div class="section-header monitoring-evaluation-header">
                <div class="header-title">
                  <el-icon class="header-icon"><Monitor /></el-icon>
                  <span>训练过程实时监控 & 多维度性能评估</span>
                </div>
              </div>
            </template>
            <div class="section-content">
              <el-tabs v-model="monitoringTab" class="monitoring-evaluation-tabs">
                <el-tab-pane label="实时监控" name="monitoring">
                  <div class="monitoring-tab-content">
                    <el-divider content-position="left" class="section-divider">
                      <span class="divider-text">
                        <el-icon><TrendCharts /></el-icon>
                        损失函数曲线
                      </span>
                    </el-divider>
                    <div class="chart-container" style="height: auto; min-height: 340px; padding-top: 10px;">
                      <div ref="lossChartRef" style="height: 300px;"></div>
                    </div>
                    
                    <el-divider content-position="left" class="section-divider">
                      <span class="divider-text">
                        <el-icon><DataAnalysis /></el-icon>
                        评估指标变化曲线
                        <el-tooltip content="评估指标需要在训练完成后才能查看" placement="top">
                          <el-icon style="margin-left: 4px; color: #909399; cursor: help;"><InfoFilled /></el-icon>
                        </el-tooltip>
                      </span>
                    </el-divider>
                    <div class="chart-container" style="height: auto; min-height: 340px; padding-top: 10px;">
                      <div ref="metricsChartRef" style="height: 300px;"></div>
                    </div>
                    
                    <el-divider content-position="left" class="section-divider">
                      <span class="divider-text">
                        <el-icon><Setting /></el-icon>
                        当前配置
                      </span>
                    </el-divider>
                    <div class="current-config">
                      <div class="config-item">
                        <span class="config-label">算法:</span>
                        <span class="config-value">{{ algorithmLabels[selectedAlgorithm] }}</span>
                      </div>
                      <div class="config-item">
                        <span class="config-label">网络结构:</span>
                        <span class="config-value">{{ networkParams.layers }}层 × {{ networkParams.nodes }}节点</span>
                      </div>
                      <div class="config-item">
                        <span class="config-label">学习率:</span>
                        <span class="config-value">{{ hyperParams.learningRate }}</span>
                      </div>
                      <div class="config-item">
                        <span class="config-label">批大小:</span>
                        <span class="config-value">{{ hyperParams.batchSize }}</span>
                      </div>
                      <div class="config-item">
                        <span class="config-label">优化器:</span>
                        <span class="config-value">{{ hyperParams.optimizer.toUpperCase() }}</span>
                      </div>
                    </div>
                  </div>
                </el-tab-pane>
                
                <el-tab-pane label="性能评估" name="evaluation">
                  <div class="evaluation-tab-content">
                    <el-tabs v-model="activeTab" type="card" class="evaluation-sub-tabs">
                      <el-tab-pane label="评估指标" name="metrics">
                        <div v-if="metrics.length > 0" class="metrics-grid">
                          <el-card class="metric-card" v-for="metric in metrics" :key="metric.key">
                            <div class="metric-header">
                              <h3>{{ metric.name }}</h3>
                              <el-tag :type="metric.tagType">{{ metric.value }}</el-tag>
                            </div>
                            <p class="metric-description">{{ metric.description }}</p>
                          </el-card>
                        </div>
                        <el-empty v-else description="暂无评估指标数据，请先完成模型训练" :image-size="120">
                          <template #image>
                            <el-icon style="font-size: 120px; color: #c0c4cc;"><DataAnalysis /></el-icon>
                          </template>
                        </el-empty>
                      </el-tab-pane>
                      
                      <el-tab-pane label="算法对比" name="comparison">
                        <div class="comparison-section">
                          <div class="comparison-header">
                            <span class="comparison-title">选择要对比的模型</span>
                            <el-button 
                              type="primary" 
                              size="small"
                              @click="loadModelComparison"
                              :disabled="comparisonModels.length < 2"
                            >
                              <el-icon><TrendCharts /></el-icon>
                              开始对比
                            </el-button>
                          </div>
                          <el-checkbox-group v-model="selectedComparisonModels" class="comparison-model-group">
                            <el-checkbox 
                              v-for="model in comparisonModels" 
                              :key="model.id" 
                              :label="model.id"
                              class="comparison-model-item"
                            >
                              <div class="model-info">
                                <div class="model-name-wrapper">
                                  <span class="model-name">{{ model.name }}</span>
                                </div>
                                <div class="model-tags-section">
                                  <el-tag 
                                    size="small" 
                                    :type="getAlgorithmTagType(model.algorithm)"
                                    class="algorithm-tag"
                                  >
                                    {{ algorithmLabels[model.algorithm] }}
                                  </el-tag>
                                  <el-tag 
                                    v-if="model.is_shared && !model.is_owner && model.share_info" 
                                    type="success" 
                                    size="small"
                                    effect="plain"
                                    class="sharer-tag"
                                  >
                                    分享者: {{ model.share_info.owner_username }}
                                  </el-tag>
                                </div>
                              </div>
                            </el-checkbox>
                          </el-checkbox-group>
                          <div class="chart-container" v-if="showComparisonChart">
                            <div ref="comparisonChartRef" style="height: 400px;"></div>
                          </div>
                          <el-empty v-else description="请选择至少两个模型进行对比分析" :image-size="120">
                            <template #image>
                              <el-icon style="font-size: 120px; color: #c0c4cc;"><DataAnalysis /></el-icon>
                            </template>
                          </el-empty>
                        </div>
                      </el-tab-pane>
                      
                      <el-tab-pane label="训练日志" name="logs">
                        <div v-if="trainingLogs.length > 0" class="training-logs">
                          <el-timeline>
                            <el-timeline-item
                              v-for="(log, index) in trainingLogs"
                              :key="index"
                              :timestamp="log.timestamp"
                              :color="log.type === 'info' ? '#409EFF' : log.type === 'warning' ? '#E6A23C' : '#F56C6C'"
                            >
                              {{ log.message }}
                            </el-timeline-item>
                          </el-timeline>
                        </div>
                        <el-empty v-else description="暂无训练日志，开始训练后将显示详细日志" :image-size="120">
                          <template #image>
                            <el-icon style="font-size: 120px; color: #c0c4cc;"><Document /></el-icon>
                          </template>
                        </el-empty>
                      </el-tab-pane>
                    </el-tabs>
                  </div>
                </el-tab-pane>
              </el-tabs>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script>
// 修复：增加了 computed 导入
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import { VideoPlay, VideoPause, DataAnalysis, DocumentChecked, TrendCharts, Clock, Setting, Monitor, Connection, Tools, Operation, FolderOpened, Folder, Filter, InfoFilled, Document, CircleCheck, Delete } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getBatteries, createTrainingTask, getTrainingRecord, updateTrainingTask, getModels } from '@/api'
import { ElMessage } from 'element-plus'

export default {
  name: 'TrainPlatform',
  components: {
    VideoPlay, VideoPause, DataAnalysis, DocumentChecked, TrendCharts, Clock, Setting, Monitor, Connection, Tools, Operation, InfoFilled, Document, CircleCheck, Delete
  },
  setup() {
    // 算法选择
    const selectedAlgorithm = ref('baseline')
    const algorithmLabels = {
      baseline: 'Baseline（传统机器学习）',
      bilstm: 'BiLSTM（双向长短期记忆网络）',
      deepphm: 'DeepHPM（深度物理信息神经网络）'
    }
    
    // 网络结构参数
    const networkParams = ref({
      layers: 2,
      nodes: 64,
      activation: 'tanh'
    })
    
    // 训练超参数
    const hyperParams = ref({
      learningRate: 0.001,
      batchSize: 32,
      epochs: 100,
      optimizer: 'adam'
    })
    
    // 数据集划分
    const datasetSplit = ref({
      trainRatio: 0.8
    })
    
    // 电芯选择
    const allCellOptions = ref([])
    const filteredCellOptions = ref([])
    const selectedDatasetType = ref('')
    const typeCounts = ref({
      train: 0,
      validation: 0,
      test: 0,
      other: 0
    })
    
    // 修复：计算可用电芯的数量，暴露出以供模板判定是否禁用按钮
    const availableCellsCount = computed(() => filteredCellOptions.value.length)
    
    const loadBatteryList = async () => {
      try {
        const response = await getBatteries({ limit: 1000 })
        if (response.data && response.data.data && Array.isArray(response.data.data)) {
          allCellOptions.value = response.data.data.map(battery => {
            const datasetType = battery.dataset_type ? String(battery.dataset_type).toLowerCase().trim() : null
            return {
              key: battery.battery_id,
              label: `电芯 #${battery.battery_id}${datasetType ? ` (${datasetType})` : ''}`,
              dataset_type: datasetType
            }
          })
        } else if (response.data && Array.isArray(response.data)) {
          allCellOptions.value = response.data.map(battery => {
            const datasetType = battery.dataset_type ? String(battery.dataset_type).toLowerCase().trim() : null
            return {
              key: battery.battery_id,
              label: `电芯 #${battery.battery_id}${datasetType ? ` (${datasetType})` : ''}`,
              dataset_type: datasetType
            }
          })
        } else {
          for (let i = 1; i <= 124; i++) {
            allCellOptions.value.push({ key: i, label: `电芯 #${i}`, dataset_type: null })
          }
        }
        calculateTypeCounts()
        filterBatteriesByType()
      } catch (error) {
        for (let i = 1; i <= 124; i++) {
          allCellOptions.value.push({ key: i, label: `电芯 #${i}`, dataset_type: null })
        }
        calculateTypeCounts()
        filterBatteriesByType()
      }
    }
    
    const calculateTypeCounts = () => {
      typeCounts.value = { train: 0, validation: 0, test: 0, other: 0 }
      allCellOptions.value.forEach(battery => {
        const type = battery.dataset_type
        if (type === 'train') typeCounts.value.train++
        else if (type === 'validation') typeCounts.value.validation++
        else if (type === 'test') typeCounts.value.test++
        else typeCounts.value.other++
      })
    }
    
    const filterBatteriesByType = () => {
      if (!selectedDatasetType.value || selectedDatasetType.value === '') {
        filteredCellOptions.value = [...allCellOptions.value] 
      } else {
        const selectedType = String(selectedDatasetType.value).toLowerCase().trim()
        filteredCellOptions.value = allCellOptions.value.filter(battery => {
          const batteryType = battery.dataset_type ? String(battery.dataset_type).toLowerCase().trim() : null
          return batteryType === selectedType
        })
      }
    }
    
    watch(selectedDatasetType, () => {
      filterBatteriesByType()
    })
    
    const getTypeLabel = (type) => {
      const labels = { train: '训练集 (Train)', validation: '验证集 (Validation)', test: '测试集 (Test)' }
      return labels[type] || type
    }
    
    const getTransferTitles = () => {
      if (selectedDatasetType.value) {
        const typeLabel = getTypeLabel(selectedDatasetType.value)
        return [`可选电芯 [${typeLabel}]`, '已选电芯']
      }
      return ['可选电芯', '已选电芯']
    }
    
    const filterMethod = (query, item) => {
      if (!query) return true
      return item.label.toLowerCase().includes(query.toLowerCase())
    }
    
    const selectedCells = ref([])
    const comparisonModels = ref([])
    const selectedComparisonModels = ref([])
    const showComparisonChart = ref(false)
    
    const trainingMetricsHistory = ref({ epochs: [], rmspe: [], mse: [], r2: [], mae: [] })
    const isTraining = ref(false)
    const currentEpoch = ref(0)
    const progressPercentage = ref(0)
    const trainingStatus = ref('')
    const currentMetrics = ref({ trainLoss: 0.5, valLoss: 0.6 })
    
    const lossChartRef = ref(null)
    const metricsChartRef = ref(null)
    const comparisonChartRef = ref(null)
    let lossChart = null
    let metricsChart = null
    let comparisonChart = null
    
    const metrics = ref([])
    const trainingLogs = ref([])
    const activeTab = ref('metrics')
    const monitoringTab = ref('monitoring')
    
    const formatTooltip = (value) => { return `${Math.round(value * 100)}%` }
    const formatMetricValue = (value, decimals = 4) => {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
      return Number(value).toFixed(decimals)
    }
    
    const onAlgorithmChange = (value) => { console.log(`选择了算法: ${value}`) }
    
    const selectAllAvailable = () => {
      selectedCells.value = filteredCellOptions.value.map(item => item.key)
    }
    
    const clearSelected = () => { selectedCells.value = [] }
    
    const startTraining = async () => {
      if (!selectedCells.value || selectedCells.value.length === 0) {
        ElMessage.warning('请至少选择一个电芯进行训练')
        return
      }
      isTraining.value = true; currentEpoch.value = 0; progressPercentage.value = 0; trainingStatus.value = ''
      
      if (lossChart) lossChart.setOption({ series: [ { data: [] }, { data: [] } ] })
      if (metricsChart) metricsChart.setOption({ series: [ { data: [] }, { data: [] }, { data: [] }, { data: [] } ] })
      
      trainingLogs.value.unshift({ timestamp: new Date().toLocaleString(), message: `开始训练 ${algorithmLabels[selectedAlgorithm.value]} 模型`, type: 'info' })
      
      const trainingData = {
        algorithm_type: selectedAlgorithm.value,
        battery_ids: selectedCells.value,
        network_params: { layers: networkParams.value.layers, nodes: networkParams.value.nodes, activation: networkParams.value.activation },
        hyperparams: { learning_rate: hyperParams.value.learningRate, batch_size: hyperParams.value.batchSize, epochs: hyperParams.value.epochs, optimizer: hyperParams.value.optimizer },
        dataset_split: { train_ratio: datasetSplit.value.trainRatio, validation_ratio: 1 - datasetSplit.value.trainRatio }
      }
      
      try {
        const response = await createTrainingTask(trainingData)
        if (response.data && response.data.success) {
          ElMessage.success('训练任务已创建，正在后台执行')
          trainingLogs.value.unshift({ timestamp: new Date().toLocaleString(), message: `训练任务已创建，模型ID: ${response.data.data.model_id}`, type: 'info' })
          currentTaskId.value = response.data.data.training_record_id
          pollTrainingProgress(currentTaskId.value)
        } else throw new Error(response.data?.message || '创建训练任务失败')
      } catch (error) {
        ElMessage.error(`训练任务创建失败: ${error.message || error}`)
        isTraining.value = false; trainingStatus.value = 'exception'
        trainingLogs.value.unshift({ timestamp: new Date().toLocaleString(), message: `训练任务创建失败: ${error.message || error}`, type: 'error' })
      }
    }
    
    let progressPollingInterval = null
    const pollTrainingProgress = async (taskId) => {
      if (progressPollingInterval) clearInterval(progressPollingInterval)
      progressPollingInterval = setInterval(async () => {
        try {
          const response = await getTrainingRecord(taskId)
          if (response.data) {
            const task = response.data
            const status = task.status
            if (task.logs || task.training_logs) {
              const rawLogs = task.logs || task.training_logs
              const logs = rawLogs.split('\n').filter(log => log.trim())
              logs.reverse().forEach(log => {
                if (log.includes('Epoch')) {
                  const epochMatch = log.match(/Epoch (\d+)\/(\d+)/)
                  if (epochMatch) {
                    const currentEpochNum = parseInt(epochMatch[1])
                    const totalEpochs = parseInt(epochMatch[2])
                    currentEpoch.value = currentEpochNum
                    progressPercentage.value = Math.min(100, Math.round((currentEpochNum / totalEpochs) * 100))
                    
                    const trainLossMatch = log.match(/Train Loss[:\s]+([\.\d]+)/i) || log.match(/train_loss[:\s]+([\.\d]+)/i)
                    const valLossMatch = log.match(/Val Loss[:\s]+([\.\d]+)/i) || log.match(/Validation Loss[:\s]+([\.\d]+)/i) || log.match(/val_loss[:\s]+([\.\d]+)/i)
                    
                    if (trainLossMatch) currentMetrics.value.trainLoss = parseFloat(trainLossMatch[1])
                    if (valLossMatch) currentMetrics.value.valLoss = parseFloat(valLossMatch[1])
                    
                    const rmspeMatch = log.match(/RMSPE[:\s]+([\-\.\d]+)/i)
                    const mseMatch = log.match(/MSE[:\s]+([\-\.\d]+)/i)
                    const maeMatch = log.match(/MAE[:\s]+([\-\.\d]+)/i)
                    const r2Match = log.match(/R2[:\s]+([\-\.\d]+)/i) || log.match(/R²[:\s]+([\-\.\d]+)/i)
                    
                    if (lossChart) {
                      const option = lossChart.getOption()
                      const newTrainData = [...(option.series[0]?.data || []), [currentEpochNum, currentMetrics.value.trainLoss]]
                      const newValData = [...(option.series[1]?.data || []), [currentEpochNum, currentMetrics.value.valLoss]]
                      lossChart.setOption({ series: [ { data: newTrainData.slice(-100) }, { data: newValData.slice(-100) } ] })
                    }
                    
                    if (metricsChart && (rmspeMatch || mseMatch || maeMatch || r2Match)) {
                      const option = metricsChart.getOption()
                      const rmspeData = [...(option.series[0]?.data || [])]
                      const mseData = [...(option.series[1]?.data || [])]
                      const maeData = [...(option.series[2]?.data || [])]
                      const r2Data = [...(option.series[3]?.data || [])]
                      
                      if (rmspeMatch) rmspeData.push([currentEpochNum, parseFloat(rmspeMatch[1])])
                      if (mseMatch) mseData.push([currentEpochNum, parseFloat(mseMatch[1])])
                      if (maeMatch) maeData.push([currentEpochNum, parseFloat(maeMatch[1])])
                      if (r2Match) r2Data.push([currentEpochNum, parseFloat(r2Match[1])])
                      
                      metricsChart.setOption({ series: [ { data: rmspeData.slice(-100) }, { data: mseData.slice(-100) }, { data: maeData.slice(-100) }, { data: r2Data.slice(-100) } ] })
                    }
                  }
                }
              })
            }
            
            if (status === 'completed') {
              clearInterval(progressPollingInterval)
              isTraining.value = false; trainingStatus.value = 'success'; progressPercentage.value = 100
              ElMessage.success('训练完成！模型已保存到数据库')
              trainingLogs.value.unshift({ timestamp: new Date().toLocaleString(), message: '训练完成，模型已保存到数据库', type: 'info' })
              try {
                const trainMetrics = task.train_metrics || {}
                const valMetrics = task.validation_metrics || {}
                metrics.value = [
                  { key: 'rmspe', name: 'RMSPE', value: `${formatMetricValue(trainMetrics.rmspe)} / ${formatMetricValue(valMetrics.rmspe)}`, description: '训练 / 验证均方根百分比误差（RMSPE）', tagType: 'success' },
                  { key: 'mse', name: 'MSE', value: `${formatMetricValue(trainMetrics.mse)} / ${formatMetricValue(valMetrics.mse)}`, description: '训练 / 验证均方误差（MSE）', tagType: 'warning' },
                  { key: 'mae', name: 'MAE', value: `${formatMetricValue(trainMetrics.mae)} / ${formatMetricValue(valMetrics.mae)}`, description: '训练 / 验证平均绝对误差（MAE）', tagType: 'success' },
                  { key: 'r2', name: 'R²', value: `${formatMetricValue(trainMetrics.r2)} / ${formatMetricValue(valMetrics.r2)}`, description: '训练 / 验证决定系数（R²，越接近1越好）', tagType: 'success' }
                ]
              } catch (e) { console.error('解析训练指标失败:', e) }
            } else if (status === 'failed' || status === 'stopped') {
              clearInterval(progressPollingInterval)
              isTraining.value = false; trainingStatus.value = 'exception'
              ElMessage.error(`训练${status === 'failed' ? '失败' : '已停止'}`)
              trainingLogs.value.unshift({ timestamp: new Date().toLocaleString(), message: `训练${status === 'failed' ? '失败' : '已停止'}`, type: status === 'failed' ? 'error' : 'warning' })
            }
          }
        } catch (error) {}
      }, 2000)
    }
    
    const currentTaskId = ref(null)
    
    const stopTraining = async () => {
      try {
        if (progressPollingInterval) { clearInterval(progressPollingInterval); progressPollingInterval = null }
        if (currentTaskId.value) { await updateTrainingTask(currentTaskId.value, { action: 'stop' }) }
        isTraining.value = false; trainingStatus.value = 'exception'
        trainingLogs.value.unshift({ timestamp: new Date().toLocaleString(), message: '训练已停止', type: 'warning' })
        ElMessage.warning('训练已停止')
      } catch (error) { ElMessage.error('停止训练失败') }
    }
    
    const initCharts = () => {
      if (lossChartRef.value) {
        if (lossChart) lossChart.dispose()
        lossChart = echarts.init(lossChartRef.value)
        lossChart.setOption({
          title: { text: '损失函数变化', left: 'center', top: 10, textStyle: { fontSize: 14, fontWeight: 'bold' } },
          tooltip: { trigger: 'axis' },
          legend: { data: ['训练损失', '验证损失'], top: 30, textStyle: { fontSize: 12 } },
          grid: { left: '12%', right: '8%', bottom: '15%', top: 60, containLabel: true },
          xAxis: { type: 'value', name: 'Epoch', nameLocation: 'middle', nameGap: 20 },
          yAxis: { type: 'value', name: 'Loss', nameLocation: 'middle', nameGap: 55 },
          series: [
            { name: '训练损失', type: 'line', data: [], smooth: true, lineStyle: { color: '#5470c6', width: 2 } },
            { name: '验证损失', type: 'line', data: [], smooth: true, lineStyle: { color: '#91cc75', width: 2 } }
          ]
        })
      }
      
      if (metricsChartRef.value) {
        if (metricsChart) metricsChart.dispose()
        metricsChart = echarts.init(metricsChartRef.value)
        metricsChart.setOption({
          title: { text: '评估指标变化', left: 'center', top: 10, textStyle: { fontSize: 14, fontWeight: 'bold' } },
          tooltip: { trigger: 'axis' },
          legend: { data: ['RMSPE', 'MSE', 'MAE', 'R²'], top: 30, textStyle: { fontSize: 12 } },
          grid: { left: '15%', right: '15%', bottom: '15%', top: 60, containLabel: true },
          xAxis: { type: 'value', name: 'Epoch', nameLocation: 'middle', nameGap: 20 },
          yAxis: [
            { type: 'value', name: '误差指标', position: 'left', nameLocation: 'middle', nameGap: 65 },
            { type: 'value', name: 'R²', position: 'right', nameLocation: 'middle', nameGap: 55, min: 0, max: 1 }
          ],
          series: [
            { name: 'RMSPE', type: 'line', data: [], smooth: true, yAxisIndex: 0, lineStyle: { color: '#ee6666', width: 2 } },
            { name: 'MSE', type: 'line', data: [], smooth: true, yAxisIndex: 0, lineStyle: { color: '#fac858', width: 2 } },
            { name: 'MAE', type: 'line', data: [], smooth: true, yAxisIndex: 0, lineStyle: { color: '#3ba272', width: 2 } },
            { name: 'R²', type: 'line', data: [], smooth: true, yAxisIndex: 1, lineStyle: { color: '#73c0de', width: 2 } }
          ]
        })
      }
    }
    
    const resizeHandler = () => {
      if (lossChart) lossChart.resize()
      if (metricsChart) metricsChart.resize()
      if (comparisonChart) comparisonChart.resize()
    }
    
    const loadComparisonModels = async () => {
      try {
        const response = await getModels()
        if (response.data && Array.isArray(response.data)) {
          comparisonModels.value = response.data.map(model => {
            let trainMetrics = {}
            let validationMetrics = {}
            if (model.metrics) {
              let metrics = typeof model.metrics === 'string' ? JSON.parse(model.metrics) : model.metrics
              trainMetrics = metrics.train || {}
              validationMetrics = metrics.validation || {}
            }
            if (model.train_metrics) trainMetrics = typeof model.train_metrics === 'string' ? JSON.parse(model.train_metrics) : model.train_metrics
            if (model.validation_metrics) validationMetrics = typeof model.validation_metrics === 'string' ? JSON.parse(model.validation_metrics) : model.validation_metrics
            
            return {
              id: model.id, name: model.name || `Model_${model.id}`, algorithm: model.algorithm || model.algorithm_type || 'unknown',
              train_metrics: trainMetrics, validation_metrics: validationMetrics,
              is_owner: model.is_owner !== undefined ? model.is_owner : true, is_shared: model.is_shared || false, share_info: model.share_info || null
            }
          })
        }
      } catch (error) {}
    }
    
    const loadModelComparison = async () => {
      if (selectedComparisonModels.value.length < 2) { ElMessage.warning('请选择至少两个模型进行对比'); return }
      showComparisonChart.value = true
      await nextTick()
      
      if (!comparisonChart && comparisonChartRef.value) comparisonChart = echarts.init(comparisonChartRef.value)
      
      const selectedModels = comparisonModels.value.filter(m => selectedComparisonModels.value.includes(m.id))
      const modelNames = selectedModels.map(m => m.name)
      
      const rmspeData = selectedModels.map(m => { const metrics = JSON.parse(JSON.stringify(m.validation_metrics || m.train_metrics || {})); return metrics.rmspe ? parseFloat(metrics.rmspe) : 0 })
      const mseData = selectedModels.map(m => { const metrics = JSON.parse(JSON.stringify(m.validation_metrics || m.train_metrics || {})); return metrics.mse ? parseFloat(metrics.mse) : 0 })
      const r2Data = selectedModels.map(m => { const metrics = JSON.parse(JSON.stringify(m.validation_metrics || m.train_metrics || {})); return metrics.r2 ? parseFloat(metrics.r2) : 0 })
      const maeData = selectedModels.map(m => { const metrics = JSON.parse(JSON.stringify(m.validation_metrics || m.train_metrics || {})); return metrics.mae ? parseFloat(metrics.mae) : 0 })
      
      const hasData = rmspeData.some(v => v > 0) || mseData.some(v => v > 0) || r2Data.some(v => v > 0) || maeData.some(v => v > 0)
      if (!hasData) ElMessage.warning('选中的模型没有有效的评估指标数据')
      
      comparisonChart.setOption({
        title: { text: '模型性能对比分析', subtext: '基于验证集的评估指标', left: 'center' },
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        legend: { data: ['RMSPE', 'MSE', 'R²', 'MAE'], top: 40 },
        grid: { left: '5%', right: '5%', bottom: '5%', top: 90, containLabel: true },
        xAxis: { type: 'value' },
        yAxis: { type: 'category', data: modelNames },
        series: [
          { name: 'RMSPE', type: 'bar', data: rmspeData, itemStyle: { color: '#ee6666' }, label: { show: true, position: 'right' } },
          { name: 'MSE', type: 'bar', data: mseData, itemStyle: { color: '#fac858' }, label: { show: true, position: 'right' } },
          { name: 'R²', type: 'bar', data: r2Data, itemStyle: { color: '#73c0de' }, label: { show: true, position: 'right' } },
          { name: 'MAE', type: 'bar', data: maeData, itemStyle: { color: '#3ba272' }, label: { show: true, position: 'right' } }
        ]
      })
      if (hasData) ElMessage.success('对比图表已生成')
    }
    
    const getAlgorithmTagType = (algorithm) => {
      const typeMap = { baseline: 'info', bilstm: 'success', deepphm: 'warning' }
      return typeMap[algorithm] || 'info'
    }
    
    onMounted(async () => {
      await loadBatteryList()
      await loadComparisonModels()
      const defaultIds = [85, 100, 124]
      selectedCells.value = defaultIds.filter(id => allCellOptions.value.some(option => option.key === id))
      if (selectedCells.value.length === 0 && allCellOptions.value.length > 0) selectedCells.value = [allCellOptions.value[0].key]
      
      await nextTick()
      setTimeout(() => { initCharts() }, 200)
      window.addEventListener('resize', resizeHandler)
    })
    
    onUnmounted(() => {
      if (lossChart) lossChart.dispose()
      if (metricsChart) metricsChart.dispose()
      if (comparisonChart) comparisonChart.dispose()
      window.removeEventListener('resize', resizeHandler)
    })
    
    watch(isTraining, (newVal) => { if (newVal) trainingStatus.value = '' })
    
    watch(monitoringTab, async (newTab) => {
      if (newTab === 'monitoring') {
        await nextTick()
        setTimeout(() => {
          if (lossChartRef.value && lossChartRef.value.clientWidth > 0) {
            if (!lossChart) initCharts()
            else lossChart.resize()
          }
        }, 150)
      }
    })
    
    // 修复：补全导出的所有方法，特别是模板用到的 availableCellsCount 和 filterBatteriesByType
    return {
      selectedAlgorithm,
      algorithmLabels,
      networkParams,
      hyperParams,
      datasetSplit,
      filteredCellOptions,
      selectedCells,
      selectedDatasetType,
      typeCounts,
      availableCellsCount,     // <- 修复：确保模板不再报错
      filterBatteriesByType,   // <- 修复：确保模板不再报错
      getTypeLabel,
      getTransferTitles,
      filterMethod,
      isTraining,
      currentEpoch,
      progressPercentage,
      trainingStatus,
      currentMetrics,
      lossChartRef,
      metricsChartRef,
      comparisonChartRef,
      metrics,
      trainingLogs,
      activeTab,
      monitoringTab,
      formatTooltip,
      onAlgorithmChange,
      selectAllAvailable,
      clearSelected,
      startTraining,
      stopTraining,
      comparisonModels,
      selectedComparisonModels,
      showComparisonChart,
      loadModelComparison,
      getAlgorithmTagType
    }
  }
}
</script>

<style scoped>
/* 原有的庞大 CSS 样式保持完全一致，无需修改，篇幅有限省略展示重复的CSS */
/* 您可以完全保留原先 <style scoped> 中的全部内容 */
.train-platform { padding: 20px; }
.card-container { min-height: 800px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
/* ... (请将原始 TrainPlatform.vue 的 <style scoped> 内容接在此处) ... */
</style>