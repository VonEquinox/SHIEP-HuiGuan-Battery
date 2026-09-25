<template>
  <div class="share-management">
    <el-card class="card-container">
      <template #header>
        <div class="card-header">
          <span>资源共享管理</span>
        </div>
      </template>
      
      <el-tabs :model-value="activeTab" type="card" @update:model-value="updateActiveTab" @tab-change="handleTabChange">
        <!-- 我分享出去的资源 -->
        <el-tab-pane label="我分享的资源" name="sent">
          <div class="tab-content">
            <div class="toolbar">
              <el-button type="primary" @click="openShareDialog(null, 'sent')">
                <el-icon><Share /></el-icon>
                分享资源
              </el-button>
            </div>
            
            <el-table
              :data="paginatedSentShares"
              stripe
              style="width: 100%"
              v-loading="sentLoading"
              empty-text="暂无分享记录"
            >
              <el-table-column prop="resource_type" label="资源类型" width="120">
                <template #default="{ row }">
                  <el-tag :type="getResourceTypeTagType(row.resource_type)">
                    {{ getResourceTypeLabel(row.resource_type) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="resource_id" label="资源ID" width="100" />
              <el-table-column prop="resource_name" label="模型名称" min-width="300" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.resource_name" style="white-space: nowrap; display: inline-block; max-width: 100%;">{{ row.resource_name }}</span>
                  <span v-else style="color: #909399;">-</span>
                </template>
              </el-table-column>
              <el-table-column prop="shared_with_username" label="分享给">
                <template #default="{ row }">
                  <span v-if="row.is_public" style="color: #67c23a;">公开（所有人可见）</span>
                  <span v-else>{{ row.shared_with_username || '未知用户' }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="permission" label="权限" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.permission === 'write' ? 'success' : 'info'">
                    {{ row.permission === 'write' ? '读写' : '只读' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="notes" label="备注" show-overflow-tooltip />
              <el-table-column prop="created_at" label="分享时间" width="180">
                <template #default="{ row }">
                  {{ formatDate(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="200" fixed="right">
                <template #default="{ row }">
                  <div style="display: flex; gap: 8px;">
                    <el-button 
                      size="small" 
                      type="primary" 
                      @click="viewResource(row)"
                    >
                      查看详情
                    </el-button>
                    <el-button 
                      size="small" 
                      type="danger" 
                      @click="cancelShare(row.id)"
                      :loading="deletingShareId === row.id"
                    >
                      取消分享
                    </el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
            
            <!-- 分页 -->
            <div class="pagination" v-if="sentSharesTotal > 0">
              <el-pagination
                current-page="sentCurrentPage"
                page-size="sentPageSize"
                :page-sizes="[10, 20, 50, 100]"
                :background="true"
                layout="total, sizes, prev, pager, next, jumper"
                :total="sentSharesTotal"
                @size-change="handleSentSizeChange"
                @current-change="handleSentCurrentChange"
              />
            </div>
          </div>
        </el-tab-pane>
        
        <!-- 我被分享的资源 -->
        <el-tab-pane label="我收到的分享" name="received">
          <div class="tab-content">
            <el-table
              :data="paginatedReceivedShares"
              stripe
              style="width: 100%"
              v-loading="receivedLoading"
              empty-text="暂无被分享的资源"
            >
              <el-table-column prop="resource_type" label="资源类型" width="120">
                <template #default="{ row }">
                  <el-tag :type="getResourceTypeTagType(row.resource_type)">
                    {{ getResourceTypeLabel(row.resource_type) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="resource_id" label="资源ID" width="100" />
              <el-table-column prop="resource_name" label="模型名称" min-width="300" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.resource_name" style="white-space: nowrap; display: inline-block; max-width: 100%;">{{ row.resource_name }}</span>
                  <span v-else style="color: #909399;">-</span>
                </template>
              </el-table-column>
              <el-table-column prop="owner_username" label="分享者" width="150" />
              <el-table-column prop="permission" label="权限" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.permission === 'write' ? 'success' : 'info'">
                    {{ row.permission === 'write' ? '读写' : '只读' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="notes" label="备注" show-overflow-tooltip />
              <el-table-column prop="created_at" label="分享时间" width="180">
                <template #default="{ row }">
                  {{ formatDate(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" fixed="right">
                <template #default="{ row }">
                  <el-button 
                    size="small" 
                    type="primary" 
                    @click="viewResource(row)"
                  >
                    查看资源
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            
            <!-- 分页 -->
            <div class="pagination" v-if="receivedSharesTotal > 0">
              <el-pagination
                current-page="receivedCurrentPage"
                page-size="receivedPageSize"
                :page-sizes="[10, 20, 50, 100]"
                :background="true"
                layout="total, sizes, prev, pager, next, jumper"
                :total="receivedSharesTotal"
                @size-change="handleReceivedSizeChange"
                @current-change="handleReceivedCurrentChange"
              />
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
    
    <!-- 分享资源对话框 -->
    <el-dialog
      v-model="shareDialogVisible"
      :title="shareDialogTitle"
      width="600px"
    >
      <el-form :model="shareForm" :rules="shareRules" ref="shareFormRef" label-width="120px">
        <el-form-item label="资源类型">
          <el-input value="模型" disabled style="width: 100%" />
          <input type="hidden" v-model="shareForm.resource_type" />
        </el-form-item>
        
        <el-form-item label="选择模型" prop="resource_ids">
          <el-select 
            v-model="shareForm.resource_ids" 
            placeholder="选择要分享的模型（可多选）"
            style="width: 100%"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            :max-collapse-tags="3"
            :loading="loadingResources"
            @change="handleResourceTypeChange"
          >
            <el-option 
              v-for="resource in availableResources"
              :key="resource.id"
              :label="resource.name || `ID: ${resource.id}`"
              :value="resource.id"
            />
          </el-select>
          <div style="margin-top: 8px; font-size: 12px; color: #909399;">
            已选择 {{ shareForm.resource_ids ? shareForm.resource_ids.length : 0 }} 个模型
          </div>
        </el-form-item>
        
        <el-form-item label="分享给用户" prop="usernames">
          <el-input
            v-model="shareForm.usernames"
            placeholder="输入用户名，多个用户名用逗号或换行分隔"
            type="textarea"
            :rows="4"
            style="width: 100%"
            @input="handleUsernameInput"
          />
          <div style="margin-top: 8px; font-size: 12px; color: #909399;">
            <div>支持批量分享：输入多个用户名，用逗号（,）或换行分隔</div>
            <div style="margin-top: 4px;">
              <el-tag
                v-for="(username, index) in usernameTags"
                :key="index"
                closable
                @close="removeUsername(username)"
                style="margin-right: 8px; margin-top: 4px;"
              >
                {{ username }}
              </el-tag>
            </div>
          </div>
        </el-form-item>
        
        <el-form-item label="权限" prop="permission">
          <el-radio-group v-model="shareForm.permission">
            <el-radio value="read">只读（可查看，不可修改）</el-radio>
            <el-radio value="write">读写（可查看和修改）</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item label="备注">
          <el-input 
            v-model="shareForm.notes" 
            type="textarea" 
            :rows="3"
            placeholder="可选：添加分享备注"
          />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="shareDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmShare" :loading="sharing">
          确认分享
        </el-button>
      </template>
    </el-dialog>
    
    <!-- 资源详情对话框 -->
    <el-dialog
      v-model="resourceDetailDialogVisible"
      :title="currentResource ? `模型详情 - ${currentResource.name}` : '模型详情'"
      width="800px"
      v-loading="loadingResourceDetail"
    >
      <template v-if="currentResource">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="模型ID">{{ currentResource.id }}</el-descriptions-item>
          <el-descriptions-item label="模型名称">{{ currentResource.name }}</el-descriptions-item>
          <el-descriptions-item label="算法类型">
            <el-tag :type="getAlgorithmTagType(currentResource.algorithm)">
              {{ getAlgorithmLabel(currentResource.algorithm) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="版本">{{ currentResource.version || 'v1.0.0' }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="currentResource.status === 'completed' ? 'success' : 'info'">
              {{ currentResource.status === 'completed' ? '已完成' : currentResource.status }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="准确率">{{ formatAccuracy(currentResource.accuracy) }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ currentResource.createdTime }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ currentResource.updatedTime }}</el-descriptions-item>
          <el-descriptions-item label="分享者" v-if="currentResource.owner_username">
            <el-tag type="success">{{ currentResource.owner_username }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="分享权限" v-if="currentResource.permission">
            <el-tag :type="currentResource.permission === 'write' ? 'success' : 'info'">
              {{ currentResource.permission === 'write' ? '读写' : '只读' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="分享时间" v-if="currentResource.shared_at">
            {{ new Date(currentResource.shared_at).toLocaleString('zh-CN') }}
          </el-descriptions-item>
          <el-descriptions-item label="描述信息" :span="2">
            {{ currentResource.description || '暂无描述信息' }}
          </el-descriptions-item>
        </el-descriptions>
        
        <!-- 性能指标 -->
        <el-divider content-position="left">性能指标</el-divider>
        <template v-if="hasPerformanceMetrics">
          <el-tabs v-model="metricsTab" type="border-card">
            <!-- 验证集指标 -->
            <el-tab-pane label="验证集指标" name="validation" v-if="hasValidationMetrics">
              <el-row :gutter="20">
                <el-col :span="6" v-if="getMetricValue('validation', 'rmspe') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('validation', 'rmspe')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">RMSPE</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('validation', 'mse') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('validation', 'mse')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">MSE</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('validation', 'r2') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #67c23a;">
                      {{ formatMetricValue(getMetricValue('validation', 'r2')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">R²</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('validation', 'mae') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('validation', 'mae')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">MAE</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('validation', 'mape') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('validation', 'mape')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">MAPE</div>
                  </div>
                </el-col>
              </el-row>
            </el-tab-pane>
            
            <!-- 训练集指标 -->
            <el-tab-pane label="训练集指标" name="train" v-if="hasTrainMetrics">
              <el-row :gutter="20">
                <el-col :span="6" v-if="getMetricValue('train', 'rmspe') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('train', 'rmspe')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">RMSPE</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('train', 'mse') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('train', 'mse')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">MSE</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('train', 'r2') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #67c23a;">
                      {{ formatMetricValue(getMetricValue('train', 'r2')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">R²</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('train', 'mae') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('train', 'mae')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">MAE</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('train', 'mape') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('train', 'mape')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">MAPE</div>
                  </div>
                </el-col>
              </el-row>
            </el-tab-pane>
            
            <!-- 测试集指标 -->
            <el-tab-pane label="测试集指标" name="test" v-if="hasTestMetrics">
              <el-row :gutter="20">
                <el-col :span="6" v-if="getMetricValue('test', 'rmspe') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('test', 'rmspe')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">RMSPE</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('test', 'mse') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('test', 'mse')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">MSE</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('test', 'r2') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #67c23a;">
                      {{ formatMetricValue(getMetricValue('test', 'r2')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">R²</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('test', 'mae') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('test', 'mae')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">MAE</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('test', 'mape') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('test', 'mape')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">MAPE</div>
                  </div>
                </el-col>
              </el-row>
            </el-tab-pane>
            
            <!-- 通用指标（如果metrics直接包含指标） -->
            <el-tab-pane label="通用指标" name="general" v-if="hasGeneralMetrics">
              <el-row :gutter="20">
                <el-col :span="6" v-if="getMetricValue('general', 'rmspe') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('general', 'rmspe')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">RMSPE</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('general', 'mse') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('general', 'mse')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">MSE</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('general', 'r2') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #67c23a;">
                      {{ formatMetricValue(getMetricValue('general', 'r2')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">R²</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('general', 'mae') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('general', 'mae')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">MAE</div>
                  </div>
                </el-col>
                <el-col :span="6" v-if="getMetricValue('general', 'mape') !== null">
                  <div style="text-align: center; padding: 15px; border: 1px solid #ebeef5; border-radius: 4px; background: #f5f7fa;">
                    <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                      {{ formatMetricValue(getMetricValue('general', 'mape')) }}
                    </div>
                    <div style="font-size: 14px; color: #606266; margin-top: 5px;">MAPE</div>
                  </div>
                </el-col>
              </el-row>
            </el-tab-pane>
          </el-tabs>
        </template>
        <div v-else style="text-align: center; padding: 20px; color: #909399;">
          暂无性能指标数据
        </div>
      </template>
      
      <template #footer>
        <el-button @click="resourceDetailDialogVisible = false">关闭</el-button>
        <el-button 
          v-if="currentResource && currentResource.resource_type === 'model'"
          type="primary" 
          @click="() => { resourceDetailDialogVisible = false; window.location.href = '/models' }"
        >
          前往模型管理
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { ref, reactive, onMounted, watch, computed } from 'vue'
import { Share } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { 
  createShare, 
  getMyShares, 
  getReceivedShares, 
  deleteShare,
  getModels,
  getModel
} from '@/api'

export default {
  name: 'ShareManagement',
  components: {
    Share
  },
  setup() {
    const route = useRoute()
    const activeTab = ref('sent')
    const sentLoading = ref(false)
    const receivedLoading = ref(false)
    const sentShares = ref([])
    const receivedShares = ref([])
    const deletingShareId = ref(null)
    
    // 分页相关
    const sentCurrentPage = ref(1)
    const sentPageSize = ref(10)
    const receivedCurrentPage = ref(1)
    const receivedPageSize = ref(10)
    
    // 计算分页后的数据
    const paginatedSentShares = computed(() => {
      const start = (sentCurrentPage.value - 1) * sentPageSize.value
      const end = start + sentPageSize.value
      return sentShares.value.slice(start, end)
    })
    
    const paginatedReceivedShares = computed(() => {
      const start = (receivedCurrentPage.value - 1) * receivedPageSize.value
      const end = start + receivedPageSize.value
      return receivedShares.value.slice(start, end)
    })
    
    // 总数
    const sentSharesTotal = computed(() => sentShares.value.length)
    const receivedSharesTotal = computed(() => receivedShares.value.length)
    
    // 分页处理函数
    const handleSentSizeChange = (val) => {
      sentPageSize.value = val
      sentCurrentPage.value = 1
    }
    
    const handleSentCurrentChange = (val) => {
      sentCurrentPage.value = val
    }
    
    const handleReceivedSizeChange = (val) => {
      receivedPageSize.value = val
      receivedCurrentPage.value = 1
    }
    
    const handleReceivedCurrentChange = (val) => {
      receivedCurrentPage.value = val
    }
    
    // 分享对话框相关
    const shareDialogVisible = ref(false)
    const shareDialogTitle = ref('分享模型')
    const shareFormRef = ref(null)
    const sharing = ref(false)
    const loadingResources = ref(false)
    const availableResources = ref([])
    const usernameTags = ref([])  // 用户名标签列表
    
    const shareForm = reactive({
      resource_type: 'model',  // 固定为 model
      resource_ids: [],  // 改为数组，支持多选
      usernames: '',  // 用户输入的原始文本
      permission: 'read',
      notes: ''
    })
    
    const shareRules = {
      resource_ids: [
        { 
          required: true, 
          message: '请至少选择一个要分享的模型', 
          trigger: 'change',
          validator: (rule, value, callback) => {
            if (!value || !Array.isArray(value) || value.length === 0) {
              callback(new Error('请至少选择一个要分享的模型'))
            } else {
              callback()
            }
          }
        }
      ],
      usernames: [
        { required: true, message: '请输入至少一个用户名', trigger: 'blur' },
        { 
          validator: (rule, value, callback) => {
            if (!value || !value.trim()) {
              callback(new Error('请输入至少一个用户名'))
            } else {
              const usernames = parseUsernames(value)
              if (usernames.length === 0) {
                callback(new Error('请输入有效的用户名'))
              } else {
                callback()
              }
            }
          },
          trigger: 'blur'
        }
      ]
    }
    
    // 解析用户名输入（支持逗号和换行分隔）
    const parseUsernames = (input) => {
      if (!input || !input.trim()) return []
      // 先按换行分隔，再按逗号分隔，然后去重和去空
      const usernames = input
        .split(/[\n,，]/)
        .map(u => u.trim())
        .filter(u => u.length > 0)
      return [...new Set(usernames)]  // 去重
    }
    
    // 处理用户名输入
    const handleUsernameInput = () => {
      usernameTags.value = parseUsernames(shareForm.usernames)
    }
    
    // 移除用户名标签
    const removeUsername = (username) => {
      usernameTags.value = usernameTags.value.filter(u => u !== username)
      // 更新输入框文本
      shareForm.usernames = usernameTags.value.join(', ')
    }
    
    // 获取资源类型标签
    const getResourceTypeLabel = (type) => {
      const labels = {
        model: '模型',
        dataset: '数据集',
        prediction: '预测结果',
        training: '训练记录'
      }
      return labels[type] || type
    }
    
    // 获取资源类型标签类型
    const getResourceTypeTagType = (type) => {
      const types = {
        model: 'success',
        dataset: 'primary',
        prediction: 'warning',
        training: 'info'
      }
      return types[type] || 'info'
    }
    
    // 格式化日期
    const formatDate = (dateString) => {
      if (!dateString) return '-'
      const date = new Date(dateString)
      return date.toLocaleString('zh-CN')
    }
    
    // 加载我分享的资源
    const loadSentShares = async () => {
      sentLoading.value = true
      try {
        const response = await getMyShares({})
        console.log('获取我分享的资源 - 完整响应:', response)
        console.log('响应数据:', response.data)
        
        // 处理不同的响应结构
        let data = []
        if (response.data) {
          // 如果直接是数组
          if (Array.isArray(response.data)) {
            data = response.data
          }
          // 如果有success字段
          else if (response.data.success && response.data.data) {
            data = response.data.data
          }
          // 如果有data字段（可能是数组）
          else if (response.data.data && Array.isArray(response.data.data)) {
            data = response.data.data
          }
          // 如果data本身就是数组
          else if (Array.isArray(response.data)) {
            data = response.data
          }
        }
        
        console.log('解析后的分享数据:', data)
        sentShares.value = data || []
        // 重置到第一页
        sentCurrentPage.value = 1
        
        if (sentShares.value.length === 0) {
          console.warn('我分享的资源列表为空')
        }
      } catch (error) {
        console.error('加载分享列表失败:', error)
        console.error('错误详情:', error.response?.data)
        ElMessage.error('加载分享列表失败: ' + (error.response?.data?.detail || error.message))
        sentShares.value = []
      } finally {
        sentLoading.value = false
      }
    }
    
    // 加载我收到的分享
    const loadReceivedShares = async () => {
      receivedLoading.value = true
      try {
        const response = await getReceivedShares({})
        console.log('获取我收到的分享 - 完整响应:', response)
        console.log('响应数据:', response.data)
        
        // 处理不同的响应结构
        let data = []
        if (response.data) {
          // 如果直接是数组
          if (Array.isArray(response.data)) {
            data = response.data
          }
          // 如果有success字段
          else if (response.data.success && response.data.data) {
            data = response.data.data
          }
          // 如果有data字段（可能是数组）
          else if (response.data.data && Array.isArray(response.data.data)) {
            data = response.data.data
          }
          // 如果data本身就是数组
          else if (Array.isArray(response.data)) {
            data = response.data
          }
        }
        
        console.log('解析后的收到分享数据:', data)
        receivedShares.value = data || []
        // 重置到第一页
        receivedCurrentPage.value = 1
        
        if (receivedShares.value.length === 0) {
          console.warn('我收到的分享列表为空')
        }
      } catch (error) {
        console.error('加载收到的分享失败:', error)
        console.error('错误详情:', error.response?.data)
        ElMessage.error('加载收到的分享失败: ' + (error.response?.data?.detail || error.message))
        receivedShares.value = []
      } finally {
        receivedLoading.value = false
      }
    }
    
    // 切换标签页
    const handleTabChange = (tabName) => {
      if (tabName === 'sent') {
        loadSentShares()
      } else if (tabName === 'received') {
        loadReceivedShares()
      }
    }
    
    // 打开分享对话框
    const openShareDialog = async (resourceType, tab) => {
      shareDialogVisible.value = true
      
      // 重置表单
      shareForm.resource_type = 'model'  // 固定为 model
      // 如果从路由参数传入单个模型ID，转换为数组
      if (resourceType === 'model' && route.query.resource_id) {
        shareForm.resource_ids = [parseInt(route.query.resource_id)]
      } else {
        shareForm.resource_ids = []
      }
      shareForm.usernames = ''
      shareForm.permission = 'read'
      shareForm.notes = ''
      usernameTags.value = []
      
      // 加载模型列表
      await handleResourceTypeChange()
    }
    
    // 资源类型变化时加载资源列表（固定为模型）
    const handleResourceTypeChange = async () => {
      loadingResources.value = true
      try {
        const response = await getModels({ limit: 1000 })
        if (response.data && Array.isArray(response.data)) {
          // 只显示自己拥有的模型（不包括共享的）
          availableResources.value = response.data.filter(m => m.is_owner === true)
        }
      } catch (error) {
        console.error('加载模型列表失败:', error)
        ElMessage.error('加载模型列表失败')
        availableResources.value = []
      } finally {
        loadingResources.value = false
      }
    }
    
    
    // 确认分享
    const confirmShare = async () => {
      if (!shareFormRef.value) return
      
      const valid = await shareFormRef.value.validate().catch(() => false)
      if (!valid) return
      
      // 解析用户名
      const usernames = parseUsernames(shareForm.usernames)
      if (usernames.length === 0) {
        ElMessage.warning('请输入至少一个用户名')
        return
      }
      
      sharing.value = true
      try {
        // 批量分享：为每个模型和每个用户名创建分享
        const shareData = {
          resource_type: 'model',
          resource_ids: shareForm.resource_ids,  // 传递模型ID数组
          usernames: usernames,  // 传递用户名数组
          permission: shareForm.permission,
          notes: shareForm.notes
        }
        
        const response = await createShare(shareData)
        
        // 处理批量分享的返回结果
        if (response.data && response.data.success) {
          const modelCount = shareForm.resource_ids.length
          const userCount = response.data.user_count || usernames.length
          const shareCount = response.data.count || 0
          let message = `成功分享 ${modelCount} 个模型给 ${userCount} 个用户（共 ${shareCount} 条分享记录）`
          
          // 如果有失败的用户，显示提示
          if (response.data.failed_users && response.data.failed_users.length > 0) {
            message += `，${response.data.failed_users.length} 个用户已存在分享`
          }
          
          ElMessage.success(message)
          shareDialogVisible.value = false
          
          // 清空表单
          shareForm.resource_ids = []
          shareForm.usernames = ''
          usernameTags.value = []
          
          // 刷新列表
          if (activeTab.value === 'sent') {
            await loadSentShares()
          }
        } else {
          ElMessage.error(response.data?.message || '分享失败')
        }
      } catch (error) {
        console.error('分享失败:', error)
        ElMessage.error(error.response?.data?.detail || error.response?.data?.message || '分享失败')
      } finally {
        sharing.value = false
      }
    }
    
    // 取消分享
    const cancelShare = async (shareId) => {
      try {
        await ElMessageBox.confirm(
          '确定要取消分享吗？',
          '确认',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning'
          }
        )
        
        deletingShareId.value = shareId
        await deleteShare(shareId)
        ElMessage.success('已取消分享')
        await loadSentShares()
      } catch (error) {
        if (error !== 'cancel') {
          console.error('取消分享失败:', error)
          ElMessage.error('取消分享失败')
        }
      } finally {
        deletingShareId.value = null
      }
    }
    
    // 查看资源详情
    const resourceDetailDialogVisible = ref(false)
    const currentResource = ref(null)
    const loadingResourceDetail = ref(false)
    const metricsTab = ref('validation')
    
    // 计算属性：检查是否有性能指标
    const hasPerformanceMetrics = computed(() => {
      if (!currentResource.value) return false
      const res = currentResource.value
      return hasValidationMetrics.value || hasTrainMetrics.value || hasTestMetrics.value || hasGeneralMetrics.value
    })
    
    const hasValidationMetrics = computed(() => {
      if (!currentResource.value || !currentResource.value.validation_metrics) return false
      const vm = currentResource.value.validation_metrics
      return vm && typeof vm === 'object' && Object.keys(vm).length > 0
    })
    
    const hasTrainMetrics = computed(() => {
      if (!currentResource.value || !currentResource.value.train_metrics) return false
      const tm = currentResource.value.train_metrics
      return tm && typeof tm === 'object' && Object.keys(tm).length > 0
    })
    
    const hasTestMetrics = computed(() => {
      if (!currentResource.value || !currentResource.value.test_metrics) return false
      const tm = currentResource.value.test_metrics
      return tm && typeof tm === 'object' && Object.keys(tm).length > 0
    })
    
    const hasGeneralMetrics = computed(() => {
      if (!currentResource.value || !currentResource.value.metrics) return false
      const m = currentResource.value.metrics
      if (!m || typeof m !== 'object') return false
      // 如果metrics包含train或validation，不算通用指标
      if (m.train || m.validation) return false
      // 检查是否有直接的指标值
      const metricKeys = ['rmspe', 'mse', 'r2', 'mae', 'mape', 'accuracy']
      return metricKeys.some(key => m[key] !== undefined && m[key] !== null)
    })
    
    // 获取指标值
    const getMetricValue = (type, metricName) => {
      if (!currentResource.value) return null
      const res = currentResource.value
      
      if (type === 'validation' && res.validation_metrics) {
        return res.validation_metrics[metricName] !== undefined ? res.validation_metrics[metricName] : null
      }
      if (type === 'train' && res.train_metrics) {
        return res.train_metrics[metricName] !== undefined ? res.train_metrics[metricName] : null
      }
      if (type === 'test' && res.test_metrics) {
        return res.test_metrics[metricName] !== undefined ? res.test_metrics[metricName] : null
      }
      if (type === 'general' && res.metrics) {
        // 确保不是嵌套结构
        if (res.metrics.train || res.metrics.validation) return null
        return res.metrics[metricName] !== undefined ? res.metrics[metricName] : null
      }
      return null
    }
    
    // 格式化指标值
    const formatMetricValue = (value) => {
      if (value === null || value === undefined) return '-'
      if (typeof value === 'number') {
        // 如果是R²，显示为百分比
        if (value <= 1 && value >= 0) {
          return (value * 100).toFixed(2) + '%'
        }
        // 其他指标保留适当小数位
        if (Math.abs(value) < 0.01) {
          return value.toExponential(2)
        }
        return value.toFixed(4)
      }
      return value
    }
    
    const viewResource = async (row) => {
      if (row.resource_type === 'model') {
        loadingResourceDetail.value = true
        try {
          // 确保resource_id是整数
          const modelId = parseInt(row.resource_id)
          const response = await getModel(modelId)
          if (response.data) {
            currentResource.value = {
              ...response.data,
              // 如果是自己分享的资源，owner_username为空（因为自己是owner）
              // 如果是收到的分享，使用row.owner_username
              owner_username: row.owner_username || null,
              permission: row.permission,
              shared_at: row.created_at
            }
            resourceDetailDialogVisible.value = true
          } else {
            ElMessage.error('获取模型详情失败')
          }
        } catch (error) {
          console.error('获取模型详情失败:', error)
          ElMessage.error('获取模型详情失败: ' + (error.response?.data?.detail || error.message))
        } finally {
          loadingResourceDetail.value = false
        }
      } else {
        ElMessage.info('该资源类型的查看功能暂未实现')
      }
    }
    
    // 格式化准确率
    const formatAccuracy = (accuracy) => {
      if (typeof accuracy === 'number') {
        return (accuracy * 100).toFixed(2) + '%'
      }
      return accuracy || '-'
    }
    
    // 获取算法标签类型
    const getAlgorithmTagType = (algorithm) => {
      const types = {
        'DeepHPM': 'warning',
        'BILSTM': 'success',
        'Baseline': 'info',
        'LSTM': 'primary',
        'GRU': 'success'
      }
      return types[algorithm] || 'info'
    }
    
    // 获取算法标签文本
    const getAlgorithmLabel = (algorithm) => {
      const labels = {
        'DeepHPM': 'DeepHPM',
        'BILSTM': 'BILSTM',
        'Baseline': 'Baseline',
        'LSTM': 'LSTM',
        'GRU': 'GRU'
      }
      return labels[algorithm] || algorithm
    }
    
    // 监听路由参数，如果是从其他页面跳转过来的，自动打开分享对话框
    watch(() => route.query, async (newQuery) => {
      if (newQuery.action === 'share' && newQuery.resource_type && newQuery.resource_id) {
        shareForm.resource_type = newQuery.resource_type
        shareForm.resource_id = parseInt(newQuery.resource_id)
        await handleResourceTypeChange()
        // 延迟打开对话框，确保资源列表已加载
        setTimeout(() => {
          openShareDialog(newQuery.resource_type, 'sent')
        }, 300)
      }
    }, { immediate: true })
    
    // 更新activeTab的函数
    const updateActiveTab = (value) => {
      activeTab.value = value
    }
    
    onMounted(() => {
      loadSentShares()
    })
    
    return {
      activeTab: activeTab,
      sentShares,
      receivedShares,
      paginatedSentShares,
      paginatedReceivedShares,
      sentSharesTotal,
      receivedSharesTotal,
      sentCurrentPage,
      sentPageSize,
      receivedCurrentPage,
      receivedPageSize,
      sentLoading,
      receivedLoading,
      deletingShareId,
      handleSentSizeChange,
      handleSentCurrentChange,
      handleReceivedSizeChange,
      handleReceivedCurrentChange,
      shareDialogVisible,
      shareDialogTitle,
      shareFormRef,
      shareForm,
      shareRules,
      sharing,
      loadingResources,
      availableResources,
      usernameTags,
      getResourceTypeLabel,
      getResourceTypeTagType,
      formatDate,
      loadSentShares,
      loadReceivedShares,
      updateActiveTab,
      handleTabChange,
      openShareDialog,
      handleResourceTypeChange,
      handleUsernameInput,
      removeUsername,
      parseUsernames,
      confirmShare,
      cancelShare,
      viewResource,
      resourceDetailDialogVisible,
      currentResource,
      loadingResourceDetail,
      metricsTab,
      hasPerformanceMetrics,
      hasValidationMetrics,
      hasTrainMetrics,
      hasTestMetrics,
      hasGeneralMetrics,
      getMetricValue,
      formatMetricValue,
      formatAccuracy,
      getAlgorithmTagType,
      getAlgorithmLabel
    }
  }
}
</script>

<style scoped>
.share-management {
  padding: 20px;
}

.card-container {
  min-height: 600px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.tab-content {
  padding: 20px 0;
}

.toolbar {
  margin-bottom: 20px;
  display: flex;
  align-items: center;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: center;
}

:deep(.el-table .cell) {
  padding: 0 5px;
}
</style>
