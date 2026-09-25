#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
更新TestPlatform.vue以连接后端API
"""

def update_test_platform():
    # 读取原始文件
    with open('frontend/src/views/TestPlatform.vue', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换import部分
    old_import = "import { ref, onMounted, onUnmounted, reactive } from 'vue'\nimport { VideoPlay, VideoPause } from '@element-plus/icons-vue'\nimport * as echarts from 'echarts'\n\nexport default {"
    
    new_import = "import { ref, onMounted, onUnmounted, reactive } from 'vue'\nimport { VideoPlay, VideoPause } from '@element-plus/icons-vue'\nimport * as echarts from 'echarts'\nimport axios from 'axios'\n\n// API 基础地址\nconst API_BASE_URL = 'http://localhost:5000/api'\n\nexport default {"
    
    content = content.replace(old_import, new_import)
    
    # 替换电池选项生成部分
    old_battery_options = "    // 电池组选项\n    const batteryOptions = ref([\n      { key: 91, label: '电池组 #91' },\n      { key: 100, label: '电池组 #100' },\n      { key: 124, label: '电池组 #124' },\n      { key: 92, label: '电池组 #92' },\n      { key: 93, label: '电池组 #93' },\n      { key: 94, label: '电池组 #94' },"
    
    new_battery_options = "    // 电池组选项\n    const batteryOptions = ref([])\n    \n    // 从API加载电池列表\n    const loadBatteryList = async () => {\n      try {\n        const response = await axios.get(`${API_BASE_URL}/batteries`)\n        if (response.data.success) {\n          batteryOptions.value = response.data.data.map(battery => ({\n            key: battery.battery_id,\n            label: `电池组 #${battery.battery_id} (${battery.dataset_type})`\n          }))\n        }\n      } catch (error) {\n        console.error('加载电池列表失败:', error)\n        // 如果API失败，使用默认列表\n        for (let i = 1; i <= 124; i++) {\n          batteryOptions.value.push({\n            key: i,\n            label: `电池组 #${i}`\n          })\n        }\n      }\n    }"
    
    content = content.replace(old_battery_options, new_battery_options)
    
    # 替换模型选项生成部分
    old_model_options = "    // 模型选项\n    const modelOptions = ref([\n      { id: 1, name: 'Baseline_20231201', algorithm: 'baseline', accuracy: 0.9567 },\n      { id: 2, name: 'BiLSTM_20231202', algorithm: 'bilstm', accuracy: 0.9789 },\n      { id: 3, name: 'DeepHPM_20231203', algorithm: 'deepphm', accuracy: 0.9876 },\n      { id: 4, name: 'Baseline_20231115', algorithm: 'baseline', accuracy: 0.8945 },\n    ])"
    
    new_model_options = "    // 模型选项\n    const modelOptions = ref([])\n    \n    // 从API加载模型列表\n    const loadModelList = async () => {\n      try {\n        const response = await axios.get(`${API_BASE_URL}/models`)\n        if (response.data.success) {\n          modelOptions.value = response.data.data\n        }\n      } catch (error) {\n        console.error('加载模型列表失败:', error)\n        // 如果API失败，使用默认列表\n        modelOptions.value = [\n          { id: 1, name: 'Baseline_20231201', algorithm: 'baseline', accuracy: 0.9567 },\n          { id: 2, name: 'BiLSTM_20231202', algorithm: 'bilstm', accuracy: 0.9789 },\n          { id: 3, name: 'DeepHPM_20231203', algorithm: 'deepphm', accuracy: 0.9876 },\n          { id: 4, name: 'Baseline_20231115', algorithm: 'baseline', accuracy: 0.8945 },\n        ]\n      }\n    }"
    
    content = content.replace(old_model_options, new_model_options)
    
    # 更新onMounted函数
    old_on_mounted = "    onMounted(() => {\n      // 初始化数据\n      initCharts()\n      window.addEventListener('resize', resizeHandler)\n    })"
    
    new_on_mounted = "    onMounted(async () => {\n      // 从API加载数据\n      await loadBatteryList()\n      await loadModelList()\n      \n      // 初始化数据\n      initCharts()\n      window.addEventListener('resize', resizeHandler)\n    })"
    
    content = content.replace(old_on_mounted, new_on_mounted)
    
    # 写回文件
    with open('frontend/src/views/TestPlatform.vue', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ TestPlatform.vue已更新，连接到后端API")

if __name__ == "__main__":
    update_test_platform()