#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
更新ModelManagement.vue以连接后端API
"""

def update_model_management():
    # 读取原始文件
    with open('frontend/src/views/ModelManagement.vue', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换import部分
    old_import = "import { ref, reactive, onMounted } from 'vue'\nimport { Plus, Refresh, Delete } from '@element-plus/icons-vue'\n\nexport default {"
    
    new_import = "import { ref, reactive, onMounted } from 'vue'\nimport { Plus, Refresh, Delete } from '@element-plus/icons-vue'\nimport axios from 'axios'\n\n// API 基础地址\nconst API_BASE_URL = 'http://localhost:5000/api'\n\nexport default {"
    
    content = content.replace(old_import, new_import)
    
    # 替换模拟数据为API调用
    old_model_list = "    // 模型列表数据\n    const modelList = ref([\n      {\n        id: 1,\n        name: 'Baseline_20231201',"
    
    new_model_list = "    // 模型列表数据\n    const modelList = ref([])\n    \n    // 从API加载模型列表\n    const loadModels = async () => {\n      loading.value = true\n      try {\n        const response = await axios.get(`${API_BASE_URL}/models`)\n        if (response.data.success) {\n          modelList.value = response.data.data\n          total.value = response.data.pagination?.total || response.data.data.length\n        }\n      } catch (error) {\n        console.error('加载模型列表失败:', error)\n        // 如果API失败，使用默认列表\n        modelList.value = [\n          {\n            id: 1,\n            name: 'Baseline_20231201',"
    
    content = content.replace(old_model_list, new_model_list)
    
    # 更新onMounted函数
    old_on_mounted = "    onMounted(() => {\n      // 初始化数据\n    })"
    
    new_on_mounted = "    onMounted(async () => {\n      await loadModels()\n    })"
    
    content = content.replace(old_on_mounted, new_on_mounted)
    
    # 写回文件
    with open('frontend/src/views/ModelManagement.vue', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ ModelManagement.vue已更新，连接到后端API")

if __name__ == "__main__":
    update_model_management()