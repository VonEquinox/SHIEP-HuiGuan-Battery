<template>
  <div class="results-analysis">
    <el-card class="card-container">
      <template #header>
        <div class="card-header">
          <span>结果分析</span>
        </div>
      </template>
      
      <!-- 控制面板 -->
      <el-row :gutter="20" style="margin-bottom: 20px;">
        <el-col :span="6">
          <el-card shadow="hover">
            <div class="control-item">
              <div class="control-label">选择算法</div>
              <el-select 
                v-model="selectedAlgorithms" 
                placeholder="选择算法" 
                multiple
                collapse-tags
                collapse-tags-tooltip
                style="width: 100%"
              >
                <el-option label="Baseline" value="baseline" />
                <el-option label="BiLSTM" value="bilstm" />
                <el-option label="DeepHPM" value="deepphm" />
              </el-select>
            </div>
          </el-card>
        </el-col>
        
        <el-col :span="6">
          <el-card shadow="hover">
            <div class="control-item">
              <div class="control-label">选择指标</div>
              <el-select 
                v-model="selectedMetrics" 
                placeholder="选择指标" 
                multiple
                collapse-tags
                collapse-tags-tooltip
                style="width: 100%"
              >
                <el-option label="RMSPE" value="rmspe" />
                <el-option label="MSE" value="mse" />
                <el-option label="R²" value="r2" />
                <el-option label="MAE" value="mae" />
                <el-option label="MAPE" value="mape" />
              </el-select>
            </div>
          </el-card>
        </el-col>
        
        <el-col :span="6">
          <el-card shadow="hover">
            <div class="control-item">
              <div class="control-label">比较类型</div>
              <el-radio-group v-model="comparisonType" style="display: block;">
                <el-radio value="algorithm">算法间比较</el-radio>
                <el-radio value="metric">指标间比较</el-radio>
              </el-radio-group>
            </div>
          </el-card>
        </el-col>
        
        <el-col :span="6">
          <el-card shadow="hover">
            <div class="control-item">
              <div class="control-label">操作</div>
              <el-button type="primary" @click="generateReport">生成报告</el-button>
              <el-button @click="exportAll">导出全部</el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>
      
      <!-- 图表展示区域 -->
      <el-row :gutter="20">
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>
              <div class="chart-header">
                <span>性能指标对比图</span>
              </div>
            </template>
            <div ref="performanceChartRef" style="height: 400px;"></div>
          </el-card>
        </el-col>
        
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>
              <div class="chart-header">
                <span>收敛性能分析</span>
              </div>
            </template>
            <div ref="convergenceChartRef" style="height: 400px;"></div>
          </el-card>
        </el-col>
      </el-row>
      
      <el-row :gutter="20" style="margin-top: 20px;">
        <el-col :span="24">
          <el-card shadow="hover">
            <template #header>
              <div class="chart-header">
                <span>预测精度分布图</span>
              </div>
            </template>
            <div ref="distributionChartRef" style="height: 400px;"></div>
          </el-card>
        </el-col>
      </el-row>
      
      <!-- 详细数据表格 -->
      <el-row :gutter="20" style="margin-top: 20px;">
        <el-col :span="24">
          <el-card shadow="hover">
            <template #header>
              <div class="chart-header">
                <span>详细性能数据</span>
                <div>
                  <el-button
                    size="small"
                    type="primary"
                    :disabled="selectedRowIds.length < 2"
                    @click="showCompareDialog"
                  >
                    对比选中模型 ({{ selectedRowIds.length }})
                  </el-button>
                </div>
              </div>
            </template>
            
            <el-table
              :data="detailedResults"
              stripe
              style="width: 100%"
              height="400"
              @selection-change="handleSelectionChange"
            >
              <el-table-column type="selection" width="55" />
              <el-table-column prop="algorithm" label="算法" width="150">
                <template #default="{ row }">
                  <el-tag 
                    :type="getAlgorithmTagType(row.algorithm)" 
                    size="small"
                  >
                    {{ getAlgorithmLabel(row.algorithm) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="rmspe" label="RMSPE" width="120">
                <template #default="{ row }">
                  <span>{{ row.rmspe.toFixed(6) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="mse" label="MSE" width="120">
                <template #default="{ row }">
                  <span>{{ row.mse.toExponential(4) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="r2" label="R²" width="120">
                <template #default="{ row }">
                  <span>{{ row.r2.toFixed(6) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="mae" label="MAE" width="120">
                <template #default="{ row }">
                  <span>{{ row.mae.toFixed(6) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="mape" label="MAPE" width="120">
                <template #default="{ row }">
                  <span>{{ (row.mape * 100).toFixed(4) }}%</span>
                </template>
              </el-table-column>
              <el-table-column prop="smape" label="SMAPE" width="120">
                <template #default="{ row }">
                  <span>{{ (row.smape * 100).toFixed(4) }}%</span>
                </template>
              </el-table-column>
              <el-table-column prop="trainingTime" label="训练时间(s)" width="120">
                <template #default="{ row }">
                  <span>{{ row.trainingTime.toFixed(2) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="parameters" label="参数量(M)" width="120">
                <template #default="{ row }">
                  <span>{{ row.parameters.toFixed(2) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="操作" fixed="right" width="100">
                <template #default="{ row }">
                  <el-button size="small" @click="viewDetails(row)">查看详情</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </el-card>
    
    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailsDialogVisible"
      title="算法详情"
      width="800px"
      :before-close="handleClose"
    >
      <el-descriptions :column="2" border>
        <el-descriptions-item label="算法名称">
          <el-tag :type="getAlgorithmTagType(currentDetail.algorithm)">
            {{ getAlgorithmLabel(currentDetail.algorithm) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="RMSPE">{{ currentDetail.rmspe.toFixed(6) }}</el-descriptions-item>
        <el-descriptions-item label="MSE">{{ currentDetail.mse.toExponential(6) }}</el-descriptions-item>
        <el-descriptions-item label="R²">{{ currentDetail.r2.toFixed(6) }}</el-descriptions-item>
        <el-descriptions-item label="MAE">{{ currentDetail.mae.toFixed(6) }}</el-descriptions-item>
        <el-descriptions-item label="MAPE">{{ (currentDetail.mape * 100).toFixed(4) }}%</el-descriptions-item>
        <el-descriptions-item label="SMAPE">{{ (currentDetail.smape * 100).toFixed(4) }}%</el-descriptions-item>
        <el-descriptions-item label="训练时间">{{ currentDetail.trainingTime.toFixed(2) }}秒</el-descriptions-item>
        <el-descriptions-item label="参数量">{{ currentDetail.parameters.toFixed(2) }}M</el-descriptions-item>
        <el-descriptions-item label="内存占用">{{ currentDetail.memoryUsage }}MB</el-descriptions-item>
        <el-descriptions-item label="收敛轮数">{{ currentDetail.convergenceEpoch }}</el-descriptions-item>
        <el-descriptions-item label="最佳验证损失">{{ currentDetail.bestValLoss.toExponential(6) }}</el-descriptions-item>
      </el-descriptions>
      
      <!-- 性能趋势图 -->
      <el-divider></el-divider>
      <div ref="trendChartRef" style="height: 300px;"></div>
      
      <template #footer>
        <el-button @click="detailsDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="exportSingleResult">导出此结果</el-button>
      </template>
    </el-dialog>
    
    <!-- 模型对比对话框 -->
    <el-dialog
      v-model="compareDialogVisible"
      title="模型对比"
      width="70%"
    >
      <div v-if="selectedModels.length > 0" style="max-height: 500px; overflow: auto;">
        <table style="width:100%; border-collapse: collapse; font-size: 14px;">
          <thead style="position: sticky; top: 0; background: #f5f7fa; z-index: 1;">
            <tr>
              <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">指标</th>
              <th
                v-for="model in selectedModels"
                :key="model.id"
                style="padding: 10px; border: 1px solid #ddd; text-align: center;"
              >
                {{ getAlgorithmLabel(model.algorithm) }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">RMSPE</td>
              <td
                v-for="model in selectedModels"
                :key="model.id"
                style="padding: 10px; border: 1px solid #ddd; text-align: center;"
              >
                {{ model.rmspe?.toFixed(6) || 'N/A' }}
              </td>
            </tr>
            <tr>
              <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">MSE</td>
              <td
                v-for="model in selectedModels"
                :key="model.id"
                style="padding: 10px; border: 1px solid #ddd; text-align: center;"
              >
                {{ model.mse?.toExponential(4) || 'N/A' }}
              </td>
            </tr>
            <tr>
              <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">R²</td>
              <td
                v-for="model in selectedModels"
                :key="model.id"
                style="padding: 10px; border: 1px solid #ddd; text-align: center;"
              >
                {{ model.r2?.toFixed(6) || 'N/A' }}
              </td>
            </tr>
            <tr>
              <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">MAE</td>
              <td
                v-for="model in selectedModels"
                :key="model.id"
                style="padding: 10px; border: 1px solid #ddd; text-align: center;"
              >
                {{ model.mae?.toFixed(6) || 'N/A' }}
              </td>
            </tr>
            <tr>
              <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">训练时间(s)</td>
              <td
                v-for="model in selectedModels"
                :key="model.id"
                style="padding: 10px; border: 1px solid #ddd; text-align: center;"
              >
                {{ model.trainingTime?.toFixed(2) || 'N/A' }}
              </td>
            </tr>
            <tr>
              <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">参数量(M)</td>
              <td
                v-for="model in selectedModels"
                :key="model.id"
                style="padding: 10px; border: 1px solid #ddd; text-align: center;"
              >
                {{ model.parameters?.toFixed(2) || 'N/A' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <template #footer>
        <el-button @click="compareDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
    
    <!-- 报告生成对话框 -->
    <el-dialog
      v-model="reportDialogVisible"
      title="生成分析报告"
      width="600px"
    >
      <el-form :model="reportForm" label-width="120px">
        <el-form-item label="报告标题">
          <el-input v-model="reportForm.title" placeholder="请输入报告标题" />
        </el-form-item>
        <el-form-item label="报告类型">
          <el-radio-group v-model="reportForm.type">
            <el-radio value="summary">摘要报告</el-radio>
            <el-radio value="detailed">详细报告</el-radio>
            <el-radio value="comparison">对比报告</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="包含内容">
          <el-checkbox-group v-model="reportForm.content">
            <el-checkbox label="charts">图表</el-checkbox>
            <el-checkbox label="tables">表格</el-checkbox>
            <el-checkbox label="statistics">统计数据</el-checkbox>
            <el-checkbox label="conclusion">结论分析</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reportDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmGenerateReport">生成报告</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, reactive, watch } from 'vue'
import * as echarts from 'echarts'
import { getPerformanceStatistics, getConvergenceData, getErrorDistribution, createModelComparison } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getUserInfo } from '@/utils/auth'

export default {
  name: 'ResultsAnalysis',
  setup() {
    // 获取当前用户信息
    const getCurrentUserId = () => {
      const userInfo = getUserInfo()
      return userInfo?.id || null
    }
    // 选择的算法
    const selectedAlgorithms = ref(['baseline', 'bilstm', 'deepphm'])
    
    // 选择的指标
    const selectedMetrics = ref(['rmspe', 'mse', 'r2'])
    
    // 比较类型
    const comparisonType = ref('algorithm')
    
    // 对比弹窗相关
    const compareDialogVisible = ref(false)
    const selectedRowIds = ref([])  // 选中的行 ID
    const selectedModels = ref([])  // 选中的模型完整数据
    
    // 存储原始 API 数据
    const rawData = ref([])
    
    // 筛选后的数据
    const filteredData = ref([])
    
    // 根据选中的算法筛选数据
    const applyFilters = () => {
      if (rawData.value.length === 0) {
        filteredData.value = []
        detailedResults.value = []
        return
      }
      
      // 按算法筛选
      const filtered = rawData.value.filter(item => {
        const alg = item.algorithm.toLowerCase()
        return selectedAlgorithms.value.some(selected => {
          const sel = selected.toLowerCase()
          return alg.includes(sel) || sel.includes(alg)
        })
      })
      
      filteredData.value = filtered
      
      // 更新表格数据
      detailedResults.value = filtered
      
      // 更新所有图表
      updatePerformanceChart(filtered)
      updateConvergenceChart(filtered)
      updateDistributionChart(filtered)
      
      console.log(`筛选后显示 ${filtered.length} 个模型`)
    }
    
    // 监听筛选条件变化
    watch([selectedAlgorithms, selectedMetrics, comparisonType], () => {
      console.log('筛选条件变化:', {
        algorithms: selectedAlgorithms.value,
        metrics: selectedMetrics.value,
        type: comparisonType.value
      })
      applyFilters()
    }, { deep: true })
    
    // 误差分布数据（来自后端；没有则使用示例）
    const distributionData = ref(null)

    // 从 API 获取结果数据
    const fetchResultsData = async () => {
      try {
        console.log('开始获取性能统计数据...')
            
        // 获取性能统计数据
        const response = await getPerformanceStatistics()
            
        console.log('API 响应:', response)
            
        if (response.data && response.data.success && response.data.data) {
          const results = response.data.data
              
          console.log(`成功获取 ${results.length} 个模型的数据`)
              
          // 保存原始数据
          rawData.value = results
          
          // 应用筛选并更新图表（会自动更新 detailedResults）
          applyFilters()
              
          ElMessage.success(`成功加载 ${results.length} 个模型的分析数据`)
        } else {
          console.warn('API 返回数据为空，使用模拟数据')
          ElMessage.warning('暂无训练数据，显示示例数据')
          
          // 清空原始数据
          rawData.value = []
          filteredData.value = []
              
          // 使用模拟数据
          updatePerformanceChart()
          updateConvergenceChart()
          updateDistributionChart()
        }

        // 获取当前用户的预测误差分布（用于“预测精度分布图”）
        try {
          const distResp = await getErrorDistribution({ bins: 20, max_error: 0.05 })
          if (distResp.data && distResp.data.success && distResp.data.data) {
            distributionData.value = distResp.data.data
            updateDistributionChart()
          }
        } catch (e) {
          console.warn('获取误差分布失败，使用示例数据:', e?.message || e)
        }
      } catch (error) {
        console.error('获取结果数据失败:', error)
        ElMessage.error('获取数据失败，显示示例数据')
        
        // 清空原始数据
        rawData.value = []
        filteredData.value = []
            
        // 如果 API 失败，使用模拟数据
        updatePerformanceChart()
        updateConvergenceChart()
        updateDistributionChart()
      }
    }
    
    // 图表引用
    const performanceChartRef = ref(null)
    const convergenceChartRef = ref(null)
    const distributionChartRef = ref(null)
    const trendChartRef = ref(null)
    
    // 图表实例
    let performanceChart = null
    let convergenceChart = null
    let distributionChart = null
    let trendChart = null
    
    // 详细结果数据
    const detailedResults = ref([
      {
        algorithm: 'baseline',
        rmspe: 0.0324,
        mse: 0.0008,
        r2: 0.9456,
        mae: 0.0187,
        mape: 0.0123,
        smape: 0.0115,
        trainingTime: 125.67,
        parameters: 2.4,
        memoryUsage: 512,
        convergenceEpoch: 87,
        bestValLoss: 0.0012
      },
      {
        algorithm: 'bilstm',
        rmspe: 0.0218,
        mse: 0.0005,
        r2: 0.9723,
        mae: 0.0152,
        mape: 0.0087,
        smape: 0.0082,
        trainingTime: 287.43,
        parameters: 4.2,
        memoryUsage: 1024,
        convergenceEpoch: 156,
        bestValLoss: 0.0008
      },
      {
        algorithm: 'deepphm',
        rmspe: 0.0156,
        mse: 0.0003,
        r2: 0.9876,
        mae: 0.0123,
        mape: 0.0065,
        smape: 0.0061,
        trainingTime: 456.78,
        parameters: 6.8,
        memoryUsage: 2048,
        convergenceEpoch: 234,
        bestValLoss: 0.0005
      }
    ])
    
    // 详情对话框
    const detailsDialogVisible = ref(false)
    const currentDetail = reactive({})
    
    // 报告对话框
    const reportDialogVisible = ref(false)
    const reportForm = reactive({
      title: '电池寿命预测算法性能分析报告',
      type: 'detailed',
      content: ['charts', 'tables', 'statistics', 'conclusion']
    })
    
    // 获取算法标签类型
    const getAlgorithmTagType = (algorithm) => {
      switch (algorithm) {
        case 'baseline': return 'info'
        case 'bilstm': return 'success'
        case 'deepphm': return 'warning'
        default: return 'info'
      }
    }
    
    // 获取算法标签文本
    const getAlgorithmLabel = (algorithm) => {
      const labels = {
        baseline: 'Baseline',
        bilstm: 'BiLSTM',
        deepphm: 'DeepHPM'
      }
      return labels[algorithm] || algorithm
    }
    
    // 查看详情
    const viewDetails = (row) => {
      Object.assign(currentDetail, row)
      detailsDialogVisible.value = true
      
      // 等待弹窗 DOM 渲染完成后初始化图表
      setTimeout(() => {
        if (trendChartRef.value && !trendChart) {
          trendChart = echarts.init(trendChartRef.value)
        }
        updateTrendChart()
      }, 100)
    }
    
    // 表格选择变化
    const handleSelectionChange = (selection) => {
      selectedRowIds.value = selection.map(row => row.id)
      selectedModels.value = selection
    }
    
    // 显示对比弹窗
    const showCompareDialog = async () => {
      if (selectedModels.value.length < 2) {
        ElMessage.warning('请至少选择2个模型进行对比')
        return
      }
      
      // 保存模型比较记录到数据库
      try {
        const currentUserId = getCurrentUserId()
        if (currentUserId) {
          const comparisonData = {
            comparison_name: `模型对比_${selectedModels.value.map(m => getAlgorithmLabel(m.algorithm)).join('_vs_')}_${new Date().toISOString().slice(0, 10)}`,
            compared_models: JSON.stringify(selectedModels.value.map(m => m.id).filter(id => id)),
            comparison_metrics: JSON.stringify(['rmspe', 'mse', 'r2', 'mae']),
            comparison_results: JSON.stringify(selectedModels.value.map(m => ({
              id: m.id,
              algorithm: m.algorithm,
              algorithmName: m.algorithmName,
              rmspe: m.rmspe,
              mse: m.mse,
              r2: m.r2,
              mae: m.mae,
              trainingTime: m.trainingTime,
              parameters: m.parameters
            }))),
            statistical_tests: null,
            visualization_data: JSON.stringify({
              comparison_type: 'manual_selection',
              selected_count: selectedModels.value.length
            }),
            created_by: currentUserId,
            is_active: true
          }
          
          await createModelComparison(comparisonData)
          console.log('模型对比记录已保存到数据库')
          ElMessage.success('模型对比记录已保存')
        } else {
          console.warn('无法获取当前用户ID，跳过保存模型比较记录')
        }
      } catch (error) {
        console.error('保存模型比较记录失败:', error)
        // 不阻塞对比功能，只记录错误
      }
      
      compareDialogVisible.value = true
    }
    
    // 关闭对话框
    const handleClose = (done) => {
      done()
    }
    
    // 生成报告
    const generateReport = () => {
      reportDialogVisible.value = true
    }
    
    // 确认生成报告
    const confirmGenerateReport = async () => {
      try {
        const form = reportForm
        
        // 检查是否有数据
        if (!detailedResults.value || detailedResults.value.length === 0) {
          ElMessage.warning('暂无数据，无法生成报告')
          return
        }
        
        console.log('生成报告，数据条数:', detailedResults.value.length)
        
        // 保存模型比较记录到数据库
        try {
          const currentUserId = getCurrentUserId()
          if (currentUserId) {
            // 按算法分组，每个算法只取最新的一条
            const groupedByAlgorithm = {}
            detailedResults.value.forEach(item => {
              const alg = item.algorithm
              if (!groupedByAlgorithm[alg] || (item.id && item.id > groupedByAlgorithm[alg].id)) {
                groupedByAlgorithm[alg] = item
              }
            })
            const uniqueData = Object.values(groupedByAlgorithm)
            
            const comparisonData = {
              comparison_name: form.title || `模型性能分析报告_${new Date().toISOString().slice(0, 10)}`,
              compared_models: JSON.stringify(uniqueData.map(m => m.id).filter(id => id)),
              comparison_metrics: JSON.stringify(['rmspe', 'mse', 'r2', 'mae', 'mape']),
              comparison_results: JSON.stringify(uniqueData.map(m => ({
                id: m.id,
                algorithm: m.algorithm,
                rmspe: m.rmspe,
                mse: m.mse,
                r2: m.r2,
                mae: m.mae,
                mape: m.mape
              }))),
              statistical_tests: null,
              visualization_data: JSON.stringify({
                performance_chart: selectedMetrics.value,
                comparison_type: comparisonType.value
              }),
              created_by: currentUserId,
              is_active: true
            }
            
            await createModelComparison(comparisonData)
            console.log('模型比较记录已保存到数据库')
          } else {
            console.warn('无法获取当前用户ID，跳过保存模型比较记录')
          }
        } catch (error) {
          console.error('保存模型比较记录失败:', error)
          // 不阻塞报告生成，只记录错误
        }
        console.log('选中内容:', form.content)
        console.log('报告类型:', form.type)
        console.log('detailedResults 数据:', detailedResults.value.map(m => ({ algorithm: m.algorithm, id: m.id })))
        
        // 根据报告类型决定显示的数据
        let displayData = detailedResults.value
        let reportSubtitle = ''
        
        // 按算法分组，每个算法只取最新的一条
        const groupedByAlgorithm = {}
        detailedResults.value.forEach(item => {
          const alg = item.algorithm
          if (!groupedByAlgorithm[alg] || item.id > groupedByAlgorithm[alg].id) {
            groupedByAlgorithm[alg] = item
          }
        })
        
        // 转换为数组
        const uniqueData = Object.values(groupedByAlgorithm)
        console.log('去重后算法数量:', uniqueData.length, uniqueData.map(m => m.algorithm))
        
        if (form.type === 'summary') {
          // 摘要报告：使用去重后的数据
          displayData = uniqueData
          reportSubtitle = `本报告提供 ${uniqueData.length} 种算法的核心性能指标摘要`
        } else if (form.type === 'detailed') {
          // 详细报告：使用去重后的数据
          displayData = uniqueData
          reportSubtitle = `本报告包含 ${uniqueData.length} 种算法的详细性能分析和对比`
        } else if (form.type === 'comparison') {
          // 对比报告：只显示前3个不同算法
          displayData = uniqueData.slice(0, 3)
          reportSubtitle = `本报告对比了 ${displayData.length} 种代表性算法的性能差异`
        }
        
        // 构建 HTML 报告
        let htmlContent = `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${form.title}</title>
  <style>
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    body {
      font-family: 'Microsoft YaHei', 'Segoe UI', Arial, sans-serif;
      max-width: 1400px;
      margin: 0 auto;
      padding: 30px;
      background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
      min-height: 100vh;
    }
    .report-header {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 50px;
      border-radius: 20px;
      margin-bottom: 40px;
      text-align: center;
      box-shadow: 0 10px 40px rgba(102, 126, 234, 0.4);
      position: relative;
      overflow: hidden;
    }
    .report-header::before {
      content: '';
      position: absolute;
      top: -50%;
      right: -50%;
      width: 200%;
      height: 200%;
      background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
      animation: pulse 15s infinite;
    }
    @keyframes pulse {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.1); }
    }
    .report-header h1 {
      margin: 0 0 15px 0;
      font-size: 36px;
      font-weight: 700;
      text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
      position: relative;
      z-index: 1;
    }
    .report-header p {
      margin: 8px 0;
      opacity: 0.95;
      font-size: 16px;
      position: relative;
      z-index: 1;
    }
    .section {
      background: white;
      padding: 35px;
      margin-bottom: 25px;
      border-radius: 15px;
      box-shadow: 0 4px 15px rgba(0,0,0,0.08);
      transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    .section:hover {
      transform: translateY(-5px);
      box-shadow: 0 8px 25px rgba(0,0,0,0.12);
    }
    .section h2 {
      color: #2c3e50;
      border-bottom: 3px solid transparent;
      border-image: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
      border-image-slice: 1;
      padding-bottom: 15px;
      margin-bottom: 25px;
      font-size: 24px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      margin: 25px 0;
      border-radius: 10px;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    th, td {
      padding: 16px;
      text-align: left;
      border-bottom: 1px solid #e8e8e8;
    }
    th {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      font-weight: 600;
      text-transform: uppercase;
      font-size: 14px;
      letter-spacing: 0.5px;
    }
    td {
      font-size: 15px;
      color: #555;
    }
    tr:nth-child(even) {
      background: #f8f9fa;
    }
    tr:hover {
      background: #e3f2fd;
      transition: background 0.3s ease;
    }
    tr:last-child td {
      border-bottom: none;
    }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 25px;
      margin: 25px 0;
    }
    .summary-card {
      background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
      padding: 25px;
      border-radius: 12px;
      border-left: 5px solid #667eea;
      transition: all 0.3s ease;
      position: relative;
      overflow: hidden;
    }
    .summary-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, transparent 100%);
      opacity: 0;
      transition: opacity 0.3s ease;
    }
    .summary-card:hover::before {
      opacity: 1;
    }
    .summary-card:hover {
      transform: translateY(-3px);
      box-shadow: 0 6px 20px rgba(102, 126, 234, 0.2);
    }
    .summary-card h3 {
      margin: 0 0 12px 0;
      color: #667eea;
      font-size: 15px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .summary-card .value {
      font-size: 32px;
      font-weight: 700;
      color: #2c3e50;
      text-shadow: 1px 1px 2px rgba(0,0,0,0.05);
    }
    .conclusion {
      background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
      padding: 25px;
      border-radius: 12px;
      border-left: 5px solid #4caf50;
      margin: 25px 0;
      box-shadow: 0 3px 10px rgba(76, 175, 80, 0.15);
    }
    .conclusion h3 {
      color: #2e7d32;
      margin: 0 0 15px 0;
      font-size: 20px;
    }
    .conclusion p {
      margin: 12px 0;
      line-height: 1.8;
      color: #333;
      font-size: 15px;
    }
    .conclusion strong {
      color: #1b5e20;
      font-weight: 600;
    }
    .footer {
      text-align: center;
      color: #999;
      padding: 30px;
      margin-top: 50px;
      font-size: 14px;
      border-top: 2px solid #e0e0e0;
    }
  </style>
</head>
<body>
  <div class="report-header">
    <h1>${form.title}</h1>
    <p>生成时间：${new Date().toLocaleString('zh-CN')}</p>
    <p>报告类型：${form.type === 'summary' ? '摘要报告' : form.type === 'detailed' ? '详细报告' : '对比报告'}</p>
    ${reportSubtitle ? `<p style="font-size: 14px; margin-top: 10px; opacity: 0.9;">${reportSubtitle}</p>` : ''}
  </div>
`
        
        // 统计数据
        if (form.content.includes('statistics')) {
          const avgRmspe = (displayData.reduce((sum, m) => sum + (m.rmspe || 0), 0) / displayData.length).toFixed(6)
          const avgR2 = (displayData.reduce((sum, m) => sum + (m.r2 || 0), 0) / displayData.length).toFixed(6)
          const avgTime = (displayData.reduce((sum, m) => sum + (m.trainingTime || 0), 0) / displayData.length).toFixed(2)
          const bestModel = displayData.reduce((best, m) => (m.r2 || 0) > (best.r2 || 0) ? m : best)
          
          htmlContent += `
  <div class="section">
    <h2>📊 统计数据</h2>
    <div class="summary-grid">
      <div class="summary-card">
        <h3>模型数量</h3>
        <div class="value">${displayData.length}</div>
      </div>
      <div class="summary-card">
        <h3>平均 RMSPE</h3>
        <div class="value">${avgRmspe}</div>
      </div>
      <div class="summary-card">
        <h3>平均 R²</h3>
        <div class="value">${avgR2}</div>
      </div>
      <div class="summary-card">
        <h3>平均训练时间</h3>
        <div class="value">${avgTime}s</div>
      </div>
      <div class="summary-card">
        <h3>最佳模型</h3>
        <div class="value">${getAlgorithmLabel(bestModel.algorithm)}</div>
      </div>
    </div>
  </div>
`
        }
        
        // 表格数据（摘要报告不显示详细表格）
        if (form.content.includes('tables') && form.type !== 'summary') {
          htmlContent += `
  <div class="section">
    <h2>📋 性能对比表</h2>
    <table>
      <thead>
        <tr>
          <th>算法</th>
          <th>RMSPE</th>
          <th>MSE</th>
          <th>R²</th>
          <th>MAE</th>
          <th>训练时间(s)</th>
          <th>参数量(M)</th>
        </tr>
      </thead>
      <tbody>
`
          displayData.forEach(row => {
            htmlContent += `
        <tr>
          <td><strong>${getAlgorithmLabel(row.algorithm)}</strong></td>
          <td>${row.rmspe?.toFixed(6) || 'N/A'}</td>
          <td>${row.mse?.toExponential(4) || 'N/A'}</td>
          <td>${row.r2?.toFixed(6) || 'N/A'}</td>
          <td>${row.mae?.toFixed(6) || 'N/A'}</td>
          <td>${row.trainingTime?.toFixed(2) || 'N/A'}</td>
          <td>${row.parameters?.toFixed(2) || 'N/A'}</td>
        </tr>
`
          })
          htmlContent += `
      </tbody>
    </table>
  </div>
`
        }
        
        // 结论分析
        if (form.content.includes('conclusion')) {
          const bestModel = displayData.reduce((best, m) => (m.r2 || 0) > (best.r2 || 0) ? m : best)
          const fastestModel = displayData.reduce((fast, m) => (m.trainingTime || Infinity) < (fast.trainingTime || Infinity) ? m : fast)
          
          let conclusionText = ''
          if (form.type === 'summary') {
            conclusionText = `在全部 ${displayData.length} 个模型中，${getAlgorithmLabel(bestModel.algorithm)} 表现最佳，建议优先选用。`
          } else if (form.type === 'comparison') {
            conclusionText = `在对比的 ${displayData.length} 个模型中，${getAlgorithmLabel(bestModel.algorithm)} 的 R² 指标最高，而 ${getAlgorithmLabel(fastestModel.algorithm)} 训练速度最快。根据实际需求选择合适的模型。`
          } else {
            conclusionText = `如果追求高精度，建议使用 ${getAlgorithmLabel(bestModel.algorithm)}；如果需要快速训练，可选择 ${getAlgorithmLabel(fastestModel.algorithm)}。`
          }
          
          htmlContent += `
  <div class="section">
    <h2>📝 结论分析</h2>
    <div class="conclusion">
      <h3>性能评价</h3>
      <p><strong>最佳性能模型：</strong>${getAlgorithmLabel(bestModel.algorithm)} (R² = ${bestModel.r2?.toFixed(6)})</p>
      <p><strong>最快训练速度：</strong>${getAlgorithmLabel(fastestModel.algorithm)} (${fastestModel.trainingTime?.toFixed(2)}s)</p>
      <p><strong>综合建议：</strong>${conclusionText}</p>
    </div>
  </div>
`
        }
        
        htmlContent += `
  <div class="footer">
    <p>电池寿命预测系统 - 结果分析报告</p>
  </div>
</body>
</html>
`
        
        // 创建下载链接
        const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8;' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.setAttribute('href', url)
        link.setAttribute('download', `${form.title}_${new Date().toISOString().slice(0,10)}.html`)
        link.style.visibility = 'hidden'
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(url)
        
        ElMessage.success('报告生成成功')
        reportDialogVisible.value = false
      } catch (error) {
        console.error('生成报告失败:', error)
        ElMessage.error('生成报告失败')
      }
    }
    
    // 导出全部
    const exportAll = () => {
      try {
        if (detailedResults.value.length === 0) {
          ElMessage.warning('暂无数据可导出')
          return
        }
        
        // 生成 CSV 内容
        let csvContent = '\ufeff'  // BOM for UTF-8
        csvContent += '"算法","RMSPE","MSE","R\u00b2","MAE","MAPE","SMAPE","训练时间(s)","参数量(M)"\n'
        
        detailedResults.value.forEach(row => {
          csvContent += `"${getAlgorithmLabel(row.algorithm)}",`
          csvContent += `"${row.rmspe?.toFixed(6) || 'N/A'}",`
          csvContent += `"${row.mse?.toExponential(4) || 'N/A'}",`
          csvContent += `"${row.r2?.toFixed(6) || 'N/A'}",`
          csvContent += `"${row.mae?.toFixed(6) || 'N/A'}",`
          csvContent += `"${row.mape ? (row.mape * 100).toFixed(4) + '%' : 'N/A'}",`
          csvContent += `"${row.smape ? (row.smape * 100).toFixed(4) + '%' : 'N/A'}",`
          csvContent += `"${row.trainingTime?.toFixed(2) || 'N/A'}",`
          csvContent += `"${row.parameters?.toFixed(2) || 'N/A'}"\n`
        })
        
        // 创建下载链接
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.setAttribute('href', url)
        link.setAttribute('download', `模型性能对比报告_${new Date().toISOString().slice(0,10)}.csv`)
        link.style.visibility = 'hidden'
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(url)
        
        ElMessage.success(`成功导出 ${detailedResults.value.length} 条数据`)
      } catch (error) {
        console.error('导出失败:', error)
        ElMessage.error('导出失败')
      }
    }
    
    // 导出单个结果
    const exportSingleResult = () => {
      try {
        // 准备导出数据
        const exportData = {
          '算法名称': getAlgorithmLabel(currentDetail.algorithm),
          'RMSPE': currentDetail.rmspe?.toFixed(6) || 'N/A',
          'MSE': currentDetail.mse?.toExponential(6) || 'N/A',
          'R²': currentDetail.r2?.toFixed(6) || 'N/A',
          'MAE': currentDetail.mae?.toFixed(6) || 'N/A',
          'MAPE': currentDetail.mape ? `${(currentDetail.mape * 100).toFixed(4)}%` : 'N/A',
          'SMAPE': currentDetail.smape ? `${(currentDetail.smape * 100).toFixed(4)}%` : 'N/A',
          '训练时间': `${currentDetail.trainingTime?.toFixed(2) || 0}秒`,
          '参数量': `${currentDetail.parameters?.toFixed(2) || 0}M`,
          '内存占用': `${currentDetail.memoryUsage || 0}MB`,
          '收敛轮数': currentDetail.convergenceEpoch || 'N/A',
          '最佳验证损失': currentDetail.bestValLoss?.toExponential(6) || 'N/A'
        }
        
        // 生成 CSV 内容
        let csvContent = '\ufeff'  // BOM for UTF-8
        csvContent += '指标,数值\n'
        
        Object.entries(exportData).forEach(([key, value]) => {
          csvContent += `"${key}","${value}"\n`
        })
        
        // 创建下载链接
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.setAttribute('href', url)
        link.setAttribute('download', `${getAlgorithmLabel(currentDetail.algorithm)}_性能报告_${new Date().toISOString().slice(0,10)}.csv`)
        link.style.visibility = 'hidden'
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(url)
        
        ElMessage.success('结果导出成功')
      } catch (error) {
        console.error('导出失败:', error)
        ElMessage.error('导出失败')
      }
    }
    
    // 更新性能对比图
    const updatePerformanceChart = (apiData = null) => {
      if (performanceChart) {
        let algorithms = ['Baseline', 'BiLSTM', 'DeepHPM']
        let seriesData = []
        
        // 如果有 API 数据，使用真实数据
        if (apiData && apiData.length > 0) {
          algorithms = apiData.map(item => {
            const alg = item.algorithm || ''
            if (alg.includes('baseline')) return 'Baseline'
            if (alg.includes('bilstm') || alg.includes('lstm')) return 'BiLSTM'
            if (alg.includes('deepphm') || alg.includes('deephpm')) return 'DeepHPM'
            return item.algorithmName || alg
          })
          
          // 根据选中的指标生成 series
          const metricConfig = {
            'rmspe': { name: 'RMSPE', color: '#ee6666', key: 'rmspe' },
            'mse': { name: 'MSE', color: '#fac858', key: 'mse' },
            'r2': { name: 'R²', color: '#73c0de', key: 'r2' },
            'mae': { name: 'MAE', color: '#91cc75', key: 'mae' },
            'mape': { name: 'MAPE', color: '#5470c6', key: 'mape' }
          }
          
          selectedMetrics.value.forEach(metric => {
            const config = metricConfig[metric]
            if (config) {
              seriesData.push({
                name: config.name,
                type: 'bar',
                data: apiData.map(item => item[config.key] || 0),
                itemStyle: { color: config.color }
              })
            }
          })
        } else {
          // 使用默认模拟数据
          const metricConfig = {
            'rmspe': { name: 'RMSPE', color: '#ee6666', data: [0.0324, 0.0218, 0.0156] },
            'mse': { name: 'MSE', color: '#fac858', data: [0.0008, 0.0005, 0.0003] },
            'r2': { name: 'R²', color: '#73c0de', data: [0.9456, 0.9723, 0.9876] },
            'mae': { name: 'MAE', color: '#91cc75', data: [0.0187, 0.0152, 0.0123] },
            'mape': { name: 'MAPE', color: '#5470c6', data: [0.0123, 0.0087, 0.0065] }
          }
          
          selectedMetrics.value.forEach(metric => {
            const config = metricConfig[metric]
            if (config) {
              seriesData.push({
                name: config.name,
                type: 'bar',
                data: config.data,
                itemStyle: { color: config.color }
              })
            }
          })
        }
        
        // 根据比较类型调整图表方向
        const isAlgorithmComparison = comparisonType.value === 'algorithm'
        
        performanceChart.setOption({
          title: {
            text: isAlgorithmComparison ? '算法性能指标对比' : '指标间对比',
            subtext: isAlgorithmComparison ? '不同算法在各项指标上的表现' : '同一算法在不同指标上的表现'
          },
          tooltip: {
            trigger: 'axis',
            axisPointer: {
              type: 'shadow'
            }
          },
          legend: {
            data: seriesData.map(s => s.name)
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            containLabel: true
          },
          xAxis: {
            type: isAlgorithmComparison ? 'value' : 'category',
            boundaryGap: isAlgorithmComparison ? [0, 0.01] : true,
            data: isAlgorithmComparison ? undefined : seriesData.map(s => s.name)
          },
          yAxis: {
            type: isAlgorithmComparison ? 'category' : 'value',
            data: isAlgorithmComparison ? algorithms : undefined
          },
          series: isAlgorithmComparison ? seriesData : algorithms.map((alg, idx) => ({
            name: alg,
            type: 'bar',
            data: seriesData.map(s => s.data[idx] || 0),
            itemStyle: { color: ['#5470c6', '#91cc75', '#fac858'][idx] }
          }))
        })
      }
    }
    
    // 更新收敛性能图
    const updateConvergenceChart = (apiData = null) => {
      if (convergenceChart) {
        // 减少 epoch 数量，只显示 100 个点
        let epochs = Array.from({ length: 100 }, (_, i) => i + 1)
        let series = []
        
        // 如果有 API 数据，尝试获取真实的收敛数据
        if (apiData && apiData.length > 0) {
          apiData.forEach(item => {
            const alg = item.algorithm || ''
            let algorithmName = 'Unknown'
            let color = '#5470c6'
            
            if (alg.includes('baseline')) {
              algorithmName = 'Baseline'
              color = '#5470c6'
            } else if (alg.includes('bilstm') || alg.includes('lstm')) {
              algorithmName = 'BiLSTM'
              color = '#91cc75'
            } else if (alg.includes('deepphm') || alg.includes('deephpm')) {
              algorithmName = 'DeepHPM'
              color = '#fac858'
            }
            
            // 生成模拟的收敛曲线（根据真实参数）
            const convergenceEpoch = item.convergenceEpoch || item.epochs || 50
            const bestValLoss = item.bestValLoss || 0.001
            const lossData = epochs.map(e => {
              if (e > convergenceEpoch) return bestValLoss + (Math.random() * 0.0001)
              return bestValLoss * Math.exp(-e / (convergenceEpoch / 3)) + (Math.random() * 0.0001)
            })
            
            series.push({
              name: algorithmName,
              type: 'line',
              data: lossData,
              smooth: true,
              lineStyle: { color },
              symbol: 'none',  // 不显示数据点标记
              sampling: 'average'  // 数据采样
            })
          })
        } else {
          // 使用默认模拟数据
          const baselineLoss = epochs.map(e => 0.5 * Math.exp(-e / 30) + 0.001 + (Math.random() * 0.0002))
          const bilstmLoss = epochs.map(e => 0.4 * Math.exp(-e / 50) + 0.0008 + (Math.random() * 0.00015))
          const deepphmLoss = epochs.map(e => 0.3 * Math.exp(-e / 70) + 0.0005 + (Math.random() * 0.0001))
          
          series = [
            {
              name: 'Baseline',
              type: 'line',
              data: baselineLoss,
              smooth: true,
              lineStyle: { color: '#5470c6' },
              symbol: 'none'
            },
            {
              name: 'BiLSTM',
              type: 'line',
              data: bilstmLoss,
              smooth: true,
              lineStyle: { color: '#91cc75' },
              symbol: 'none'
            },
            {
              name: 'DeepHPM',
              type: 'line',
              data: deepphmLoss,
              smooth: true,
              lineStyle: { color: '#fac858' },
              symbol: 'none'
            }
          ]
        }
        
        convergenceChart.setOption({
          title: {
            text: '模型收敛性能对比',
            subtext: '各算法训练损失随轮数变化'
          },
          tooltip: {
            trigger: 'axis',
            axisPointer: {
              type: 'cross'
            },
            formatter: function(params) {
              let result = `Epoch ${params[0].axisValue}<br/>`
              params.forEach(item => {
                result += `${item.marker} ${item.seriesName}: ${item.value.toFixed(6)}<br/>`
              })
              return result
            }
          },
          legend: {
            data: series.map(s => s.name),
            top: 30
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            top: '15%',
            containLabel: true
          },
          xAxis: {
            type: 'category',
            boundaryGap: false,
            data: epochs,
            name: 'Epoch',
            nameLocation: 'middle',
            nameGap: 30
          },
          yAxis: {
            type: 'value',
            min: 0,
            name: '损失值',
            nameLocation: 'middle',
            nameGap: 50
          },
          series: series
        })
      }
    }
    
    // 更新分布图
    const updateDistributionChart = () => {
      if (distributionChart) {
        const dist = distributionData.value
        
        // 默认：示例数据（当后端无数据时兜底）
        let xData = []
        let baselineHist = []
        let bilstmHist = []
        let deepphmHist = []

        if (dist && dist.x && dist.series) {
          xData = dist.x.map(v => Number(v).toFixed(4))
          baselineHist = dist.series.baseline || new Array(xData.length).fill(0)
          bilstmHist = dist.series.bilstm || new Array(xData.length).fill(0)
          deepphmHist = dist.series.deepphm || new Array(xData.length).fill(0)
        } else {
          // 生成示例误差分布数据
          const baselineErrors = Array.from({ length: 1000 }, () => Math.abs(Math.random() * 0.05))
          const bilstmErrors = Array.from({ length: 1000 }, () => Math.abs(Math.random() * 0.035))
          const deepphmErrors = Array.from({ length: 1000 }, () => Math.abs(Math.random() * 0.025))
          
          const bins = 20
          const binWidth = 0.05 / bins
          baselineHist = new Array(bins).fill(0)
          bilstmHist = new Array(bins).fill(0)
          deepphmHist = new Array(bins).fill(0)
          
          baselineErrors.forEach(err => {
            const bin = Math.min(Math.floor(err / binWidth), bins - 1)
            baselineHist[bin]++
          })
          
          bilstmErrors.forEach(err => {
            const bin = Math.min(Math.floor(err / binWidth), bins - 1)
            bilstmHist[bin]++
          })
          
          deepphmErrors.forEach(err => {
            const bin = Math.min(Math.floor(err / binWidth), bins - 1)
            deepphmHist[bin]++
          })
          
          xData = Array.from({ length: bins }, (_, i) => (i * binWidth + binWidth / 2).toFixed(4))
        }
        
        distributionChart.setOption({
          title: {
            text: '预测误差分布对比',
            subtext: '不同算法预测误差的分布情况'
          },
          tooltip: {
            trigger: 'axis'
          },
          legend: {
            data: ['Baseline', 'BiLSTM', 'DeepHPM']
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            containLabel: true
          },
          xAxis: {
            type: 'category',
            data: xData
          },
          yAxis: {
            type: 'value'
          },
          series: [
            {
              name: 'Baseline',
              type: 'bar',
              data: baselineHist,
              itemStyle: {
                color: 'rgba(84, 112, 198, 0.7)'
              }
            },
            {
              name: 'BiLSTM',
              type: 'bar',
              data: bilstmHist,
              itemStyle: {
                color: 'rgba(145, 204, 117, 0.7)'
              }
            },
            {
              name: 'DeepHPM',
              type: 'bar',
              data: deepphmHist,
              itemStyle: {
                color: 'rgba(250, 200, 88, 0.7)'
              }
            }
          ]
        })
      }
    }
    
    // 更新趋势图
    const updateTrendChart = () => {
      if (trendChart) {
        // 生成模拟的趋势数据
        const epochs = Array.from({ length: 100 }, (_, i) => i + 1)
        const lossValues = epochs.map(e => currentDetail.bestValLoss * Math.exp(-e / (currentDetail.convergenceEpoch / 3)) + (Math.random() * 0.0001))
        
        trendChart.setOption({
          title: {
            text: '训练趋势',
            subtext: '损失值随训练轮数的变化'
          },
          tooltip: {
            trigger: 'axis'
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
            data: epochs
          },
          yAxis: {
            type: 'value'
          },
          series: [{
            name: '验证损失',
            type: 'line',
            data: lossValues,
            smooth: true,
            lineStyle: {
              color: '#5470c6'
            }
          }]
        })
      }
    }
    
    // 初始化图表
    const initCharts = () => {
      if (performanceChartRef.value) {
        performanceChart = echarts.init(performanceChartRef.value)
      }
      
      if (convergenceChartRef.value) {
        convergenceChart = echarts.init(convergenceChartRef.value)
      }
      
      if (distributionChartRef.value) {
        distributionChart = echarts.init(distributionChartRef.value)
      }
      
      // trendChart 在弹窗中，打开弹窗时再初始化
      
      // 更新所有图表
      updatePerformanceChart()
      updateConvergenceChart()
      updateDistributionChart()
    }
    
    // 监听窗口大小变化
    const resizeHandler = () => {
      if (performanceChart) performanceChart.resize()
      if (convergenceChart) convergenceChart.resize()
      if (distributionChart) distributionChart.resize()
      if (trendChart) trendChart.resize()
    }
    
    onMounted(async () => {
      // 初始化所有图表
      initCharts()
      window.addEventListener('resize', resizeHandler)
      
      // 从API获取数据
      await fetchResultsData()
    })
    
    onUnmounted(() => {
      if (performanceChart) performanceChart.dispose()
      if (convergenceChart) convergenceChart.dispose()
      if (distributionChart) distributionChart.dispose()
      if (trendChart) trendChart.dispose()
      window.removeEventListener('resize', resizeHandler)
    })
    
    return {
      selectedAlgorithms,
      selectedMetrics,
      comparisonType,
      performanceChartRef,
      convergenceChartRef,
      distributionChartRef,
      trendChartRef,
      detailedResults,
      detailsDialogVisible,
      currentDetail,
      reportDialogVisible,
      reportForm,
      // 对比功能
      compareDialogVisible,
      selectedRowIds,
      selectedModels,
      handleSelectionChange,
      showCompareDialog,
      // 工具函数
      getAlgorithmTagType,
      getAlgorithmLabel,
      viewDetails,
      handleClose,
      generateReport,
      confirmGenerateReport,
      exportAll,
      exportSingleResult
    }
  }
}
</script>

<style scoped>
.results-analysis {
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

.control-item {
  padding: 10px 0;
}

.control-label {
  margin-bottom: 8px;
  font-weight: bold;
  color: #606266;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

:deep(.el-table .cell) {
  padding: 0 5px;
}

@media (max-width: 768px) {
  .el-col {
    margin-bottom: 20px;
  }
}
</style>