<template>
  <div class="update-actual-value">
    <el-card>
      <template #header>
        <span>更新预测实际值</span>
      </template>
      
      <el-form :model="form" label-width="120px">
        <el-form-item label="预测记录ID">
          <el-input-number v-model="form.predictionId" :min="1" placeholder="输入预测记录ID" />
        </el-form-item>
        
        <el-form-item label="实际 SOH">
          <el-input-number 
            v-model="form.actualSoh" 
            :min="0" 
            :max="1" 
            :step="0.001"
            :precision="3"
            placeholder="输入实际SOH值 (0-1)"
          />
        </el-form-item>
        
        <el-form-item label="实际 RUL">
          <el-input-number 
            v-model="form.actualRul" 
            :min="0"
            placeholder="输入实际RUL值（循环次数）"
          />
        </el-form-item>
        
        <el-form-item label="实际 PCL">
          <el-input-number 
            v-model="form.actualPcl" 
            :min="0"
            placeholder="输入实际PCL值"
          />
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="submitUpdate" :loading="loading">
            更新实际值
          </el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
      
      <el-divider />
      
      <div v-if="result">
        <h3>更新结果</h3>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="记录ID">{{ result.id }}</el-descriptions-item>
          <el-descriptions-item label="预测SOH">{{ result.predicted_soh?.toFixed(3) || 'N/A' }}</el-descriptions-item>
          <el-descriptions-item label="实际SOH">{{ result.actual_soh?.toFixed(3) || 'N/A' }}</el-descriptions-item>
          <el-descriptions-item label="SOH误差">
            {{ result.predicted_soh && result.actual_soh ? 
               (Math.abs(result.predicted_soh - result.actual_soh) * 100).toFixed(2) + '%' : 'N/A' }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>
  </div>
</template>

<script>
import { ref, reactive } from 'vue'
import { updatePredictionActualValue } from '@/api'
import { ElMessage } from 'element-plus'

export default {
  name: 'UpdateActualValue',
  setup() {
    const form = reactive({
      predictionId: null,
      actualSoh: null,
      actualRul: null,
      actualPcl: null
    })
    
    const loading = ref(false)
    const result = ref(null)
    
    const submitUpdate = async () => {
      if (!form.predictionId) {
        ElMessage.warning('请输入预测记录ID')
        return
      }
      
      if (form.actualSoh === null && form.actualRul === null && form.actualPcl === null) {
        ElMessage.warning('请至少输入一个实际值')
        return
      }
      
      try {
        loading.value = true
        const data = {}
        if (form.actualSoh !== null) data.actual_soh = form.actualSoh
        if (form.actualRul !== null) data.actual_rul = form.actualRul
        if (form.actualPcl !== null) data.actual_pcl = form.actualPcl
        
        const response = await updatePredictionActualValue(form.predictionId, data)
        
        if (response.data && response.data.success) {
          result.value = response.data.data
          ElMessage.success('实际值更新成功')
        } else {
          ElMessage.error('更新失败')
        }
      } catch (error) {
        console.error('更新实际值失败:', error)
        ElMessage.error(error.response?.data?.detail || '更新失败')
      } finally {
        loading.value = false
      }
    }
    
    const resetForm = () => {
      form.predictionId = null
      form.actualSoh = null
      form.actualRul = null
      form.actualPcl = null
      result.value = null
    }
    
    return {
      form,
      loading,
      result,
      submitUpdate,
      resetForm
    }
  }
}
</script>

<style scoped>
.update-actual-value {
  padding: 20px;
}
</style>
