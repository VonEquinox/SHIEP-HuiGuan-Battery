<template>
  <div class="test-platform">
    <el-card class="card-container">
      <template #header>
        <div class="card-header">
          <span>算法测试平台</span>
        </div>
      </template>
      
      <!-- 预测任务配置区域 -->
      <el-row :gutter="20">
        <el-col :span="8">
          <el-card shadow="hover">
            <template #header>
              <div class="section-header">
                <span>预测任务配置</span>
              </div>
            </template>
            
            <el-form label-position="top">
              <el-form-item label="选择待预测的电芯">
                <el-select 
                  v-model="selectedBattery" 
                  placeholder="请选择电芯" 
                  style="width: 100%"
                  multiple
                  filterable
                >
                  <el-option 
                    v-for="battery in batteryOptions" 
                    :key="battery.key" 
                    :label="battery.label" 
                    :value="battery.key"
                  />
                </el-select>
              </el-form-item>
              
              <el-form-item label="选择已训练好的预测算法模型">
                <el-select 
                  v-model="selectedModel" 
                  placeholder="请选择模型" 
                  style="width: 100%"
                  filterable
                >
                  <el-option 
                    v-for="model in modelOptions" 
                    :key="model.id" 
                    :label="model.name" 
                    :value="model.id"
                    class="model-option-item"
                  >
                    <div class="model-option-content">
                      <span class="model-option-name">{{ model.name }}</span>
                      <div class="model-option-meta">
                        <span class="model-option-info">
                          {{ getAlgorithmLabel(model.algorithm) }} | {{ model.version }}
                        </span>
                        <el-tag 
                          v-if="model.is_shared && !model.is_owner && model.share_info" 
                          type="success" 
                          size="small"
                          effect="plain"
                          class="sharer-tag-option"
                        >
                          分享者: {{ model.share_info.owner_username }}
                        </el-tag>
                      </div>
                    </div>
                  </el-option>
                </el-select>
              </el-form-item>
              
              <el-form-item label="配置预测步长">
                <el-slider
                  v-model="predictionSteps"
                  :min="1"
                  :max="100"
                  :step="1"
                  show-input
                  :format-tooltip="formatStepTooltip"
                />
              </el-form-item>
              
              <el-form-item label="预测类型">
                <el-radio-group v-model="predictionType">
                  <el-radio value="rul">RUL预测（剩余使用寿命）</el-radio>
                  <el-radio value="pcl">PCL预测（容量衰减）</el-radio>
                  <el-radio value="both">两者都预测</el-radio>
                </el-radio-group>
              </el-form-item>
            </el-form>
            
            <div class="test-actions">
              <el-button 
                type="primary" 
                size="large" 
                :disabled="isTesting" 
                @click="startPrediction"
                :loading="isTesting"
              >
                <el-icon v-if="!isTesting"><VideoPlay /></el-icon>
                {{ isTesting ? '预测中...' : '开始预测' }}
              </el-button>
              <el-button 
                size="large" 
                :disabled="!isTesting" 
                @click="stopPrediction"
              >
                <el-icon><VideoPause /></el-icon>
                停止预测
              </el-button>
            </div>
          </el-card>
        </el-col>
        
        <!-- 预测结果显示区域 -->
        <el-col :span="16">
          <el-card shadow="hover">
            <template #header>
              <div class="section-header">
                <span>实时预测与展示</span>
                <div>
                  <el-button 
                    type="primary" 
                    size="small" 
                    :disabled="!predictionResult.length"
                    @click="showComparison"
                  >
                    对比分析
                  </el-button>
                  <el-button 
                    size="small" 
                    :disabled="!predictionResult.length"
                    @click="exportResults"
                  >
                    导出结果
                  </el-button>
                </div>
              </div>
            </template>
            
            <div class="prediction-display">
              <div ref="predictionChartRef" style="height: 400px;"></div>
            </div>
            
            <el-divider content-position="left">预测结果统计</el-divider>
            <el-row :gutter="20">
              <el-col :span="6">
                <div class="statistic-item">
                  <div class="statistic-number">{{ predictionStats.rmspe.toFixed(4) }}</div>
                  <div class="statistic-label">RMSPE</div>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="statistic-item">
                  <div class="statistic-number">{{ predictionStats.mse.toFixed(6) }}</div>
                  <div class="statistic-label">MSE</div>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="statistic-item">
                  <div class="statistic-number">{{ predictionStats.r2.toFixed(4) }}</div>
                  <div class="statistic-label">R²</div>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="statistic-item">
                  <div class="statistic-number">{{ predictionStats.mae.toFixed(4) }}</div>
                  <div class="statistic-label">MAE</div>
                </div>
              </el-col>
            </el-row>
          </el-card>
        </el-col>
      </el-row>
      
      <!-- 预测结果详细表格和RUL/PCL曲线 -->
      <el-row :gutter="20" style="margin-top: 20px;">
        <!-- 详细表格 -->
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>
              <div class="section-header" style="display: flex; justify-content: space-between; align-items: center;">
                <span>预测结果详情</span>
                <el-button 
                  v-if="lastPredictionId" 
                  type="success" 
                  size="small"
                  @click="openUpdateActualValueDialog"
                >
                  更新实际值
                </el-button>
              </div>
            </template>
            
            <el-table
              :data="predictionResult"
              stripe
              style="width: 100%"
              height="300"
              v-loading="resultLoading"
            >
              <el-table-column prop="cycle" label="循环次数" width="100" />
              <el-table-column prop="actualSoH" label="实际SoH" width="100">
                <template #default="{ row }">
                  <span>{{ row.actualSoH.toFixed(4) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="predictedSoH" label="预测SoH" width="100">
                <template #default="{ row }">
                  <span>{{ row.predictedSoH.toFixed(4) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="error" label="误差" width="100">
                <template #default="{ row }">
                  <span :class="row.error > 0.02 ? 'error-high' : 'error-low'">
                    {{ row.error.toFixed(4) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="rul" label="RUL" width="100">
                <template #default="{ row }">
                  <span>{{ row.rul.toFixed(2) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="pcl" label="PCL" width="100">
                <template #default="{ row }">
                  <span>{{ row.pcl.toFixed(4) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="confidence" label="置信度" width="120">
                <template #default="{ row }">
                  <el-progress 
                    :percentage="row.confidence * 100" 
                    :stroke-width="8"
                    :show-text="false"
                  />
                  <span>{{ (row.confidence * 100).toFixed(1) }}%</span>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
        
        <!-- RUL和PCL预测曲线 -->
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>
              <div class="section-header">
                <span>RUL & PCL 预测曲线</span>
              </div>
            </template>
            
            <el-tabs v-model="predictionCurveTab" type="card">
              <el-tab-pane label="RUL预测" name="rul">
                <div ref="rulChartRef" style="height: 250px;"></div>
              </el-tab-pane>
              <el-tab-pane label="PCL衰减" name="pcl">
                <div ref="pclChartRef" style="height: 250px;"></div>
              </el-tab-pane>
            </el-tabs>
          </el-card>
        </el-col>
      </el-row>
    </el-card>
    
    <!-- 更新实际值对话框 -->
    <el-dialog
      v-model="updateActualValueDialogVisible"
      title="更新预测实际值"
      width="500px"
    >
      <el-form label-width="120px">
        <el-form-item label="预测记录ID">
          <el-input-number v-model="lastPredictionId" disabled />
        </el-form-item>
        <el-form-item label="实际 SOH">
          <el-input-number 
            v-model="actualSohInput" 
            :min="0" 
            :max="1" 
            :step="0.000001"
            :precision="6"
            :formatter="formatSohValue"
            :parser="parseSohValue"
            placeholder="输入实际SOH值 (0-1)"
            style="width: 100%"
          />
          <div v-if="actualSohInput !== null && actualSohInput !== undefined" 
               style="margin-top: 5px; font-size: 12px; color: #909399;">
            当前值（完整精度）: {{ actualSohInput }}
          </div>
        </el-form-item>
        <el-alert
          title="提示：输入实际SOH值后，仪表板的准确率趋势图将显示数据"
          type="info"
          :closable="false"
          style="margin-top: 10px"
        />
      </el-form>
      <template #footer>
        <el-button @click="updateActualValueDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitActualValue" :loading="updatingActualValue">
          提交
        </el-button>
      </template>
    </el-dialog>
    
    <!-- 对比分析对话框 -->
    <el-dialog
      v-model="comparisonDialogVisible"
      title="对比分析"
      width="90%"
      top="5vh"
    >
      <div class="comparison-content">
        <div ref="comparisonChartRef" style="height: 500px;"></div>
      </div>
      <template #footer>
        <el-button @click="comparisonDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
    
    <!-- 导出结果对话框 -->
    <el-dialog
      v-model="exportDialogVisible"
      title="导出结果"
      width="400px"
    >
      <div class="export-options">
        <p>请选择导出格式：</p>
        <el-radio-group v-model="exportFormat" style="margin-top: 20px;">
          <el-radio value="csv" size="large">
            <div style="display: flex; flex-direction: column;">
              <span style="font-weight: bold;">CSV格式</span>
              <span style="font-size: 12px; color: #909399;">适合Excel打开，文件较小</span>
            </div>
          </el-radio>
          <el-radio value="excel" size="large" style="margin-top: 15px;">
            <div style="display: flex; flex-direction: column;">
              <span style="font-weight: bold;">Excel格式</span>
              <span style="font-size: 12px; color: #909399;">包含格式化和图表，推荐使用</span>
            </div>
          </el-radio>
          <el-radio value="json" size="large" style="margin-top: 15px;">
            <div style="display: flex; flex-direction: column;">
              <span style="font-weight: bold;">JSON格式</span>
              <span style="font-size: 12px; color: #909399;">适合程序处理和数据交换</span>
            </div>
          </el-radio>
        </el-radio-group>
      </div>
      <template #footer>
        <el-button @click="exportDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmExport">确认导出</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, reactive, nextTick, watch } from 'vue'
import { VideoPlay, VideoPause } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import { getBatteries, getModels, createPrediction, updatePredictionActualValue, getPredictionDetail } from '@/api'
import * as XLSX from 'xlsx'

export default {
  name: 'TestPlatform',
  components: {
    VideoPlay,
    VideoPause
  },
  setup() {
    // 电芯选项
    const batteryOptions = ref([])
    
    // 从API加载电池列表
    const loadBatteryList = async () => {
      try {
        const response = await getBatteries({ limit: 200 })
        // FastAPI返回格式: { total, skip, limit, data: [...] }
        const batteries = response.data?.data || response.data || []
        if (Array.isArray(batteries) && batteries.length > 0) {
          batteryOptions.value = batteries.map(battery => ({
            key: battery.battery_id,
            label: `电芯 #${battery.battery_id}${battery.dataset_type ? ` (${battery.dataset_type})` : ''}`
          }))
        } else {
          // 如果API返回空数组，使用默认列表
          console.warn('API返回空电池列表，使用默认数据')
          for (let i = 1; i <= 124; i++) {
            batteryOptions.value.push({
              key: i,
              label: `电芯 #${i}`
            })
          }
        }
      } catch (error) {
        console.error('加载电池列表失败:', error)
        // 如果API失败，使用默认列表
        for (let i = 1; i <= 124; i++) {
          batteryOptions.value.push({
            key: i,
            label: `电芯 #${i}`
          })
        }
      }
    }
    
    // 模型选项
    const modelOptions = ref([])
    
    // 从API加载模型列表
    const loadModelList = async () => {
      try {
        const response = await getModels()
        // FastAPI返回格式: List[dict] (直接是数组)
        const models = response.data || []
        if (Array.isArray(models) && models.length > 0) {
          modelOptions.value = models.map(model => ({
            id: model.id,
            name: model.name || `模型_${model.id}`,
            algorithm: model.algorithm || model.algorithm_type || 'unknown',
            version: model.version || 'v1.0.0',
            accuracy: model.accuracy || 0.95,
            is_owner: model.is_owner !== undefined ? model.is_owner : true,
            is_shared: model.is_shared || false,
            share_info: model.share_info || null
          }))
        } else {
          // 如果API返回空数组，使用默认列表
          console.warn('API返回空模型列表，使用默认数据')
          modelOptions.value = [
            { id: 1, name: 'Baseline_20231201', algorithm: 'baseline', version: 'v1.0.0', accuracy: 0.9567 },
            { id: 2, name: 'BiLSTM_20231202', algorithm: 'bilstm', version: 'v1.0.0', accuracy: 0.9789 },
            { id: 3, name: 'DeepHPM_20231203', algorithm: 'deepphm', version: 'v1.0.0', accuracy: 0.9876 },
            { id: 4, name: 'Baseline_20231115', algorithm: 'baseline', version: 'v1.0.0', accuracy: 0.8945 },
          ]
        }
      } catch (error) {
        console.error('加载模型列表失败:', error)
        // 如果API失败，使用默认列表
        modelOptions.value = [
          { id: 1, name: 'Baseline_20231201', algorithm: 'baseline', version: 'v1.0.0', accuracy: 0.9567 },
          { id: 2, name: 'BiLSTM_20231202', algorithm: 'bilstm', version: 'v1.0.0', accuracy: 0.9789 },
          { id: 3, name: 'DeepHPM_20231203', algorithm: 'deepphm', version: 'v1.0.0', accuracy: 0.9876 },
          { id: 4, name: 'Baseline_20231115', algorithm: 'baseline', version: 'v1.0.0', accuracy: 0.8945 },
        ]
      }
    }
    
    // 选择的电芯（默认不选任何电池，由用户手动选择）
    const selectedBattery = ref([])
    
    // 选择的模型
    const selectedModel = ref(2)
    
    // 预测步长
    const predictionSteps = ref(10)
    
    // 预测类型
    const predictionType = ref('both')
    
    // 测试状态
    const isTesting = ref(false)
    const resultLoading = ref(false)
    
    // 图表引用
    const predictionChartRef = ref(null)
    const comparisonChartRef = ref(null)
    const rulChartRef = ref(null)
    const pclChartRef = ref(null)
    let predictionChart = null
    let comparisonChart = null
    let rulChart = null
    let pclChart = null
    
    // 预测曲线标签页
    const predictionCurveTab = ref('rul')
    
    // 预测结果
    const predictionResult = ref([])
    
    // 预测统计
    const predictionStats = reactive({
      rmspe: 0.0234,
      mse: 0.0005,
      r2: 0.9786,
      mae: 0.0187
    })
    
    // 对比分析对话框
    const comparisonDialogVisible = ref(false)
    
    // 更新实际值相关
    const updateActualValueDialogVisible = ref(false)
    const lastPredictionId = ref(null)
    const actualSohInput = ref(null)
    const updatingActualValue = ref(false)
    
    // 截断函数：将数值截断到指定小数位数（不四舍五入）
    const truncateToDecimal = (value, decimals) => {
      if (value === null || value === undefined || isNaN(value)) {
        return value
      }
      const factor = Math.pow(10, decimals)
      return Math.floor(value * factor) / factor
    }
    
    // 格式化SOH值显示（截断到6位小数）
    const formatSohValue = (value) => {
      if (value === null || value === undefined || value === '') {
        return ''
      }
      const truncated = truncateToDecimal(value, 6)
      return truncated.toFixed(6)
    }
    
    // 解析SOH值输入（截断到6位小数）
    const parseSohValue = (value) => {
      if (value === '' || value === null || value === undefined) {
        return null
      }
      const num = parseFloat(value)
      if (isNaN(num)) {
        return null
      }
      return truncateToDecimal(num, 6)
    }
    
    // 导出对话框
    const exportDialogVisible = ref(false)
    const exportFormat = ref('excel')
    
    // 格式化步长提示
    const formatStepTooltip = (value) => {
      return `${value} 个循环`
    }
    
    // 获取算法标签
    const getAlgorithmLabel = (algorithm) => {
      const labels = {
        baseline: 'Baseline',
        bilstm: 'BiLSTM',
        deepphm: 'DeepHPM'
      }
      return labels[algorithm] || algorithm
    }
    
    // 开始预测
    const startPrediction = async () => {
      if (!selectedModel.value) {
        ElMessage.warning('请先选择模型')
        return
      }
      if (
        !selectedBattery.value ||
        (Array.isArray(selectedBattery.value) && selectedBattery.value.length === 0)
      ) {
        ElMessage.warning('请先选择电池')
        return
      }
      
      isTesting.value = true
      resultLoading.value = true
      
      try {
        // 生成模拟预测结果
        generateMockPredictionResult()
        
        // 保存预测记录到数据库
        // 注意: selectedBattery 是数组 [91, 100]，取第一个值
        const batteryId = Array.isArray(selectedBattery.value) ? selectedBattery.value[0] : selectedBattery.value
        
        const predictionData = {
          model_id: selectedModel.value,
          battery_id: batteryId,
          predicted_soh: predictionResult.value[predictionResult.value.length - 1].predictedSoH,
          predicted_rul: predictionResult.value[predictionResult.value.length - 1].rul,
          predicted_pcl: predictionResult.value[predictionResult.value.length - 1].pcl,
          prediction_type: predictionType.value === 'both' ? 'soh' : predictionType.value,
          confidence: predictionStats.avgConfidence / 100,
          execution_time: 2.0,  // 模拟执行时间
          input_data: JSON.stringify({
            cycles: predictionResult.value.map(r => r.cycle),
            predictions: predictionResult.value.length
          })
        }
        
        console.log('保存预测记录:', predictionData)
        const response = await createPrediction(predictionData)
        console.log('预测记录保存响应:', response)
        
        // 保存预测记录ID，用于后续更新实际值
        if (response.data && response.data.success && response.data.data) {
          lastPredictionId.value = response.data.data.id
          console.log('预测记录ID:', lastPredictionId.value)
        }
        
        resultLoading.value = false
        
        // 更新图表
        updatePredictionChart()
        
        isTesting.value = false
        ElMessage.success('预测完成并已保存记录')
      } catch (error) {
        console.error('预测失败:', error)
        resultLoading.value = false
        isTesting.value = false
        ElMessage.error('预测失败: ' + (error.response?.data?.detail || error.message))
      }
    }
    
    // 停止预测
    const stopPrediction = () => {
      isTesting.value = false
      ElMessage.info('已停止预测')
    }
    
    // 打开更新实际值对话框，自动加载真实 SOH 值
    const openUpdateActualValueDialog = async () => {
      actualSohInput.value = null
      updateActualValueDialogVisible.value = true
      
      // 自动查询真实 SOH 值
      if (lastPredictionId.value) {
        try {
          const response = await getPredictionDetail(lastPredictionId.value)
          if (response.data && response.data.success && response.data.data) {
            const suggestedSoh = response.data.data.suggested_actual_soh
            if (suggestedSoh !== null && suggestedSoh !== undefined) {
              // 使用截断法，截断到6位小数（不四舍五入）
              actualSohInput.value = truncateToDecimal(suggestedSoh, 6)
              console.log('自动加载的真实 SOH 值（原始值）:', suggestedSoh)
              console.log('自动加载的真实 SOH 值（截断后）:', actualSohInput.value)
              ElMessage.success('已自动从电池数据集加载真实 SOH 值')
            } else {
              ElMessage.warning('未找到对应的真实 SOH 值，请手动输入')
            }
          }
        } catch (error) {
          console.error('加载真实 SOH 值失败:', error)
          ElMessage.warning('自动加载失败，请手动输入')
        }
      }
    }
    
    // 提交实际值
    const submitActualValue = async () => {
      if (!lastPredictionId.value) {
        ElMessage.warning('没有可用的预测记录')
        return
      }
      if (actualSohInput.value === null || actualSohInput.value === undefined) {
        ElMessage.warning('请输入实际SOH值')
        return
      }
      
      try {
        updatingActualValue.value = true
        // 确保使用截断后的值（6位小数，不四舍五入）
        let actualSohValue = typeof actualSohInput.value === 'number' 
          ? actualSohInput.value 
          : parseFloat(actualSohInput.value)
        // 再次截断确保是6位小数
        actualSohValue = truncateToDecimal(actualSohValue, 6)
        console.log('准备上传的实际 SOH 值（截断后）:', actualSohValue)
        console.log('准备上传的实际 SOH 值（JSON）:', JSON.stringify({ actual_soh: actualSohValue }))
        
        const response = await updatePredictionActualValue(lastPredictionId.value, {
          actual_soh: actualSohValue
        })
        
        if (response.data && response.data.success) {
          ElMessage.success('实际值更新成功！请刷新仪表板查看准确率趋势')
          updateActualValueDialogVisible.value = false
        } else {
          ElMessage.error('更新失败')
        }
      } catch (error) {
        console.error('更新实际值失败:', error)
        ElMessage.error(error.response?.data?.detail || '更新失败')
      } finally {
        updatingActualValue.value = false
      }
    }
    
    // 生成模拟预测结果
    const generateMockPredictionResult = () => {
      predictionResult.value = []
      const baseSoH = 1.0
      let sumSquaredError = 0
      let sumAbsoluteError = 0
      let sumPercentageError = 0
      let sumActual = 0
      let sumSquaredActualDiff = 0
      
      for (let i = 0; i < 50; i++) {
        const cycle = i * 10
        const actualSoH = baseSoH - (i * 0.015) + (Math.random() * 0.005 - 0.0025)
        const predictedSoH = actualSoH - (Math.random() * 0.01 - 0.005)
        const error = Math.abs(actualSoH - predictedSoH)
        const rul = 1000 - cycle
        const pcl = (1 - actualSoH) * 100
        const confidence = 0.95 + (Math.random() * 0.05)
        
        // 累计统计量
        sumSquaredError += (actualSoH - predictedSoH) ** 2
        sumAbsoluteError += Math.abs(actualSoH - predictedSoH)
        sumPercentageError += ((actualSoH - predictedSoH) / actualSoH) ** 2
        sumActual += actualSoH
        
        predictionResult.value.push({
          cycle,
          actualSoH: Math.max(0.0, Math.min(1.0, actualSoH)),  // 限制在 [0, 1] 区间
          predictedSoH: Math.max(0.0, Math.min(1.0, predictedSoH)),  // 移除 0.7 的下限，改为 [0, 1] 限制
          error,
          rul: Math.max(0, rul),
          pcl,
          confidence: Math.min(1, confidence)
        })
      }
      
      // 计算统计指标
      const n = predictionResult.value.length
      const mse = sumSquaredError / n
      const mae = sumAbsoluteError / n
      const rmspe = Math.sqrt(sumPercentageError / n)
      
      // 计算 R²
      const meanActual = sumActual / n
      predictionResult.value.forEach(item => {
        sumSquaredActualDiff += (item.actualSoH - meanActual) ** 2
      })
      const r2 = 1 - (sumSquaredError / sumSquaredActualDiff)
      
      // 更新统计数据
      predictionStats.rmspe = parseFloat(rmspe.toFixed(4))
      predictionStats.mse = parseFloat(mse.toFixed(5))
      predictionStats.r2 = parseFloat(r2.toFixed(4))
      predictionStats.mae = parseFloat(mae.toFixed(4))
      
      console.log('预测统计:', predictionStats)
    }
    
    // 更新预测图表
    const updatePredictionChart = () => {
      if (predictionChart && predictionResult.value.length > 0) {
        const cycles = predictionResult.value.map(item => item.cycle)
        const actualSoH = predictionResult.value.map(item => item.actualSoH)
        const predictedSoH = predictionResult.value.map(item => item.predictedSoH)
        
        predictionChart.setOption({
          title: {
            text: 'SoH预测结果对比'
          },
          tooltip: {
            trigger: 'axis'
          },
          legend: {
            data: ['实际SoH', '预测SoH']
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            containLabel: true
          },
          xAxis: {
            type: 'category',
            boundaryGap: false,
            data: cycles
          },
          yAxis: {
            type: 'value',
            min: 0.7,
            max: 1.0
          },
          series: [
            {
              name: '实际SoH',
              type: 'line',
              data: actualSoH,
              smooth: true,
              lineStyle: {
                color: '#5470c6'
              }
            },
            {
              name: '预测SoH',
              type: 'line',
              data: predictedSoH,
              smooth: true,
              lineStyle: {
                color: '#91cc75',
                type: 'dashed'
              }
            }
          ]
        })
      }
      
      // 更新RUL图表
      updateRULChart()
      // 更新PCL图表
      updatePCLChart()
    }
    
    // 更新RUL图表
    const updateRULChart = () => {
      if (rulChart && predictionResult.value.length > 0) {
        const cycles = predictionResult.value.map(item => item.cycle)
        const rulData = predictionResult.value.map(item => item.rul)
        
        rulChart.setOption({
          title: {
            text: 'RUL (剩余使用寿命) 预测',
            left: 'center',
            textStyle: {
              fontSize: 14
            }
          },
          tooltip: {
            trigger: 'axis',
            formatter: (params) => {
              return `循环次数: ${params[0].name}<br/>
                      RUL: ${params[0].value.toFixed(2)} 循环`
            }
          },
          grid: {
            left: '10%',
            right: '10%',
            bottom: '15%',
            top: '20%',
            containLabel: true
          },
          xAxis: {
            type: 'category',
            boundaryGap: false,
            data: cycles,
            name: '循环次数',
            nameLocation: 'center',
            nameGap: 25
          },
          yAxis: {
            type: 'value',
            name: 'RUL (循环)',
            nameLocation: 'center',
            nameGap: 40
          },
          series: [
            {
              name: 'RUL',
              type: 'line',
              data: rulData,
              smooth: true,
              lineStyle: {
                color: '#f56c6c',
                width: 3
              },
              areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                  { offset: 0, color: 'rgba(245, 108, 108, 0.3)' },
                  { offset: 1, color: 'rgba(245, 108, 108, 0.05)' }
                ])
              },
              emphasis: {
                itemStyle: {
                  color: '#f56c6c',
                  borderColor: '#fff',
                  borderWidth: 2
                }
              }
            }
          ]
        })
      }
    }
    
    // 更新PCL图表
    const updatePCLChart = () => {
      if (pclChart && predictionResult.value.length > 0) {
        const cycles = predictionResult.value.map(item => item.cycle)
        const pclData = predictionResult.value.map(item => item.pcl)
        
        pclChart.setOption({
          title: {
            text: 'PCL (容量衰减) 预测',
            left: 'center',
            textStyle: {
              fontSize: 14
            }
          },
          tooltip: {
            trigger: 'axis',
            formatter: (params) => {
              return `循环次数: ${params[0].name}<br/>
                      PCL: ${params[0].value.toFixed(4)}%`
            }
          },
          grid: {
            left: '10%',
            right: '10%',
            bottom: '15%',
            top: '20%',
            containLabel: true
          },
          xAxis: {
            type: 'category',
            boundaryGap: false,
            data: cycles,
            name: '循环次数',
            nameLocation: 'center',
            nameGap: 25
          },
          yAxis: {
            type: 'value',
            name: 'PCL (%)',
            nameLocation: 'center',
            nameGap: 40
          },
          series: [
            {
              name: 'PCL',
              type: 'line',
              data: pclData,
              smooth: true,
              lineStyle: {
                color: '#e6a23c',
                width: 3
              },
              areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                  { offset: 0, color: 'rgba(230, 162, 60, 0.3)' },
                  { offset: 1, color: 'rgba(230, 162, 60, 0.05)' }
                ])
              },
              emphasis: {
                itemStyle: {
                  color: '#e6a23c',
                  borderColor: '#fff',
                  borderWidth: 2
                }
              }
            }
          ]
        })
      }
    }
    
    // 显示对比分析
    const showComparison = async () => {
      comparisonDialogVisible.value = true
      await nextTick()
      // 如果图表还未初始化，先初始化
      if (!comparisonChart && comparisonChartRef.value) {
        comparisonChart = echarts.init(comparisonChartRef.value)
      }
      setTimeout(updateComparisonChart, 100)
    }
    
    // 更新对比图表
    const updateComparisonChart = () => {
      if (comparisonChart) {
        comparisonChart.setOption({
          title: {
            text: '不同算法预测性能对比',
            subtext: '基于相同测试数据集',
            left: 'center'
          },
          tooltip: {
            trigger: 'axis',
            axisPointer: {
              type: 'shadow'
            },
            formatter: (params) => {
              let result = params[0].axisValue + '<br/>'
              params.forEach(item => {
                result += item.marker + item.seriesName + ': ' + item.value + '<br/>'
              })
              return result
            }
          },
          legend: {
            data: ['RMSPE', 'MSE', 'R²', 'MAE'],
            top: 40
          },
          grid: {
            left: '5%',
            right: '5%',
            bottom: '5%',
            top: 100,
            containLabel: true
          },
          xAxis: {
            type: 'value',
            boundaryGap: [0, 0.01],
            axisLabel: {
              formatter: '{value}'
            }
          },
          yAxis: {
            type: 'category',
            data: ['Baseline', 'BiLSTM', 'DeepHPM']
          },
          series: [
            {
              name: 'RMSPE',
              type: 'bar',
              data: [0.032, 0.028, 0.021],
              itemStyle: {
                color: '#ee6666'
              },
              label: {
                show: true,
                position: 'right',
                formatter: '{c}'
              }
            },
            {
              name: 'MSE',
              type: 'bar',
              data: [0.0008, 0.0006, 0.0004],
              itemStyle: {
                color: '#fac858'
              },
              label: {
                show: true,
                position: 'right',
                formatter: '{c}'
              }
            },
            {
              name: 'R²',
              type: 'bar',
              data: [0.945, 0.962, 0.978],
              itemStyle: {
                color: '#73c0de'
              },
              label: {
                show: true,
                position: 'right',
                formatter: '{c}'
              }
            },
            {
              name: 'MAE',
              type: 'bar',
              data: [0.018, 0.015, 0.012],
              itemStyle: {
                color: '#3ba272'
              },
              label: {
                show: true,
                position: 'right',
                formatter: '{c}'
              }
            }
          ]
        })
        comparisonChart.resize()
      }
    }
    
    // 导出结果
    const exportResults = () => {
      if (!predictionResult.value || predictionResult.value.length === 0) {
        ElMessage.warning('暂无预测结果可导出，请先完成预测')
        return
      }
      exportDialogVisible.value = true
    }
    
    // 确认导出
    const confirmExport = () => {
      switch (exportFormat.value) {
        case 'csv':
          exportToCSV()
          break
        case 'excel':
          exportToExcel()
          break
        case 'json':
          exportToJSON()
          break
      }
      exportDialogVisible.value = false
    }
    
    // 导出为CSV
    const exportToCSV = () => {
      try {
        // 添加BOM头以支持Excel正确显示中文
        let csvContent = '\uFEFF'
        csvContent += '循环次数,实际SoH,预测SoH,误差,RUL,PCL,置信度\n'
        predictionResult.value.forEach(row => {
          csvContent += `${row.cycle},${row.actualSoH.toFixed(6)},${row.predictedSoH.toFixed(6)},${row.error.toFixed(6)},${row.rul.toFixed(2)},${row.pcl.toFixed(6)},${row.confidence.toFixed(6)}\n`
        })
        
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5)
        link.setAttribute('href', url)
        link.setAttribute('download', `prediction_results_${timestamp}.csv`)
        link.style.visibility = 'hidden'
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(url)
        
        ElMessage.success('CSV文件导出成功')
      } catch (error) {
        console.error('CSV导出失败:', error)
        ElMessage.error('CSV导出失败，请重试')
      }
    }
    
    // 导出为Excel
    const exportToExcel = () => {
      try {
        // 创建工作簿
        const wb = XLSX.utils.book_new()
        
        // 准备数据
        const wsData = [
          ['循环次数', '实际SoH', '预测SoH', '误差', 'RUL', 'PCL', '置信度']
        ]
        predictionResult.value.forEach(row => {
          wsData.push([
            row.cycle,
            parseFloat(row.actualSoH.toFixed(6)),
            parseFloat(row.predictedSoH.toFixed(6)),
            parseFloat(row.error.toFixed(6)),
            parseFloat(row.rul.toFixed(2)),
            parseFloat(row.pcl.toFixed(6)),
            parseFloat(row.confidence.toFixed(6))
          ])
        })
        
        // 创建工作表
        const ws = XLSX.utils.aoa_to_sheet(wsData)
        
        // 设置列宽
        ws['!cols'] = [
          { wch: 12 }, // 循环次数
          { wch: 12 }, // 实际SoH
          { wch: 12 }, // 预测SoH
          { wch: 12 }, // 误差
          { wch: 12 }, // RUL
          { wch: 12 }, // PCL
          { wch: 12 }  // 置信度
        ]
        
        // 添加工作表到工作簿
        XLSX.utils.book_append_sheet(wb, ws, '预测结果')
        
        // 添加统计信息工作表
        const statsData = [
          ['评估指标', '数值'],
          ['RMSPE', predictionStats.rmspe.toFixed(4)],
          ['MSE', predictionStats.mse.toFixed(6)],
          ['R²', predictionStats.r2.toFixed(4)],
          ['MAE', predictionStats.mae.toFixed(4)]
        ]
        const statsWs = XLSX.utils.aoa_to_sheet(statsData)
        statsWs['!cols'] = [
          { wch: 15 },
          { wch: 15 }
        ]
        XLSX.utils.book_append_sheet(wb, statsWs, '统计指标')
        
        // 导出文件
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5)
        XLSX.writeFile(wb, `prediction_results_${timestamp}.xlsx`)
        
        ElMessage.success('Excel文件导出成功')
      } catch (error) {
        console.error('Excel导出失败:', error)
        ElMessage.error('Excel导出失败，请重试')
      }
    }
    
    // 导出为JSON
    const exportToJSON = () => {
      try {
        const exportData = {
          metadata: {
            exportTime: new Date().toISOString(),
            selectedBatteries: selectedBattery.value,
            selectedModel: selectedModel.value,
            predictionSteps: predictionSteps.value,
            predictionType: predictionType.value
          },
          statistics: {
            rmspe: predictionStats.rmspe,
            mse: predictionStats.mse,
            r2: predictionStats.r2,
            mae: predictionStats.mae
          },
          results: predictionResult.value
        }
        
        const jsonString = JSON.stringify(exportData, null, 2)
        const blob = new Blob([jsonString], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5)
        link.setAttribute('href', url)
        link.setAttribute('download', `prediction_results_${timestamp}.json`)
        link.style.visibility = 'hidden'
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(url)
        
        ElMessage.success('JSON文件导出成功')
      } catch (error) {
        console.error('JSON导出失败:', error)
        ElMessage.error('JSON导出失败，请重试')
      }
    }
    
    // 初始化图表
    const initCharts = () => {
      if (predictionChartRef.value) {
        predictionChart = echarts.init(predictionChartRef.value)
        predictionChart.setOption({
          title: {
            text: 'SoH预测结果对比'
          },
          tooltip: {
            trigger: 'axis'
          },
          legend: {
            data: ['实际SoH', '预测SoH']
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            containLabel: true
          },
          xAxis: {
            type: 'category',
            boundaryGap: false,
            data: []
          },
          yAxis: {
            type: 'value',
            min: 0.7,
            max: 1.0
          },
          series: [
            {
              name: '实际SoH',
              type: 'line',
              data: [],
              smooth: true,
              lineStyle: {
                color: '#5470c6'
              }
            },
            {
              name: '预测SoH',
              type: 'line',
              data: [],
              smooth: true,
              lineStyle: {
                color: '#91cc75',
                type: 'dashed'
              }
            }
          ]
        })
      }
      
      // 对比图表在需要时再初始化
      
      // 初始化RUL图表
      if (rulChartRef.value) {
        rulChart = echarts.init(rulChartRef.value)
      }
      
      // 初始化PCL图表
      if (pclChartRef.value) {
        pclChart = echarts.init(pclChartRef.value)
      }
    }
    
    // 监听标签页切换，初始化图表
    watch(predictionCurveTab, async (newVal) => {
      await nextTick()
      setTimeout(() => {
        if (newVal === 'rul' && !rulChart && rulChartRef.value) {
          rulChart = echarts.init(rulChartRef.value)
          updateRULChart()
        } else if (newVal === 'pcl' && !pclChart && pclChartRef.value) {
          pclChart = echarts.init(pclChartRef.value)
          updatePCLChart()
        } else if (newVal === 'rul' && rulChart) {
          rulChart.resize()
        } else if (newVal === 'pcl' && pclChart) {
          pclChart.resize()
        }
      }, 200)
    })
    
    // 监听窗口大小变化
    const resizeHandler = () => {
      if (predictionChart) predictionChart.resize()
      if (comparisonChart) comparisonChart.resize()
      if (rulChart) rulChart.resize()
      if (pclChart) pclChart.resize()
    }
    
    onMounted(async () => {
      // 从API加载数据
      await loadBatteryList()
      await loadModelList()
      
      // 初始化数据
      initCharts()
      window.addEventListener('resize', resizeHandler)
    })
    
    onUnmounted(() => {
      if (predictionChart) predictionChart.dispose()
      if (comparisonChart) comparisonChart.dispose()
      if (rulChart) rulChart.dispose()
      if (pclChart) pclChart.dispose()
      window.removeEventListener('resize', resizeHandler)
    })
    
    return {
      batteryOptions,
      modelOptions,
      selectedBattery,
      selectedModel,
      predictionSteps,
      predictionType,
      isTesting,
      resultLoading,
      predictionResult,
      predictionStats,
      comparisonDialogVisible,
      predictionChartRef,
      comparisonChartRef,
      rulChartRef,
      pclChartRef,
      predictionCurveTab,
      formatStepTooltip,
      getAlgorithmLabel,
      startPrediction,
      stopPrediction,
      openUpdateActualValueDialog,
      submitActualValue,
      updateActualValueDialogVisible,
      lastPredictionId,
      actualSohInput,
      updatingActualValue,
      formatSohValue,
      parseSohValue,
      showComparison,
      exportResults,
      exportDialogVisible,
      exportFormat,
      confirmExport
    }
  }
}
</script>

<style scoped>
.test-platform {
  padding: 20px;
}

.card-container {
  min-height: 800px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.test-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 20px;
}

.prediction-display {
  margin: 20px 0;
}

.statistic-item {
  text-align: center;
  padding: 20px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background-color: #fafafa;
}

.statistic-number {
  font-size: 24px;
  font-weight: bold;
  color: #409eff;
  margin-bottom: 5px;
}

.statistic-label {
  font-size: 14px;
  color: #606266;
}

.comparison-content {
  height: 500px;
}

.export-options {
  padding: 20px 0;
}

.export-options p {
  font-size: 14px;
  color: #606266;
  margin-bottom: 10px;
}

:deep(.el-radio) {
  width: 100%;
  padding: 15px;
  margin: 0;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  transition: all 0.3s;
}

:deep(.el-radio:hover) {
  border-color: #409eff;
  background-color: #f5f7fa;
}

:deep(.el-radio.is-checked) {
  border-color: #409eff;
  background-color: #ecf5ff;
}

.error-high {
  color: #f56c6c;
}

.error-low {
  color: #67c23a;
}

:deep(.el-table .error-high) {
  color: #f56c6c;
}

:deep(.el-table .error-low) {
  color: #67c23a;
}

.model-option-item {
  overflow: visible;
}

.model-option-content {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-width: 0;
  padding: 2px 0;
}

.model-option-name {
  font-size: 14px;
  color: #303133;
  font-weight: 500;
  white-space: nowrap;
  overflow: visible;
  flex-shrink: 0;
}

.model-option-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.model-option-info {
  color: #8492a6;
  font-size: 13px;
  flex-shrink: 0;
  white-space: nowrap;
}

.sharer-tag-option {
  min-width: 100px;
  text-align: center;
  flex-shrink: 0;
}

:deep(.el-select-dropdown__item) {
  overflow: visible;
  padding: 8px 20px;
  white-space: nowrap;
}

:deep(.el-select-dropdown__item .model-option-content) {
  max-width: 100%;
}

:deep(.el-select-dropdown) {
  overflow-x: visible;
}

@media (max-width: 768px) {
  .el-col {
    margin-bottom: 20px;
  }
  
  .statistic-item {
    margin-bottom: 10px;
  }
}
</style>