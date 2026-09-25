#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
更新TrainPlatform.vue以连接后端API
"""

def update_train_platform():
    # 读取原始文件
    with open('frontend/src/views/TrainPlatform.vue', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换import部分
    old_import = "import { ref, onMounted, onUnmounted, watch } from 'vue'\nimport { VideoPlay, VideoPause } from '@element-plus/icons-vue'\nimport * as echarts from 'echarts'\n\nexport default {"
    
    new_import = "import { ref, onMounted, onUnmounted, watch } from 'vue'\nimport { VideoPlay, VideoPause } from '@element-plus/icons-vue'\nimport * as echarts from 'echarts'\nimport axios from 'axios'\n\n// API 基础地址\nconst API_BASE_URL = 'http://localhost:5000/api'\n\nexport default {"
    
    # 替换import部分
    content = content.replace(old_import, new_import)
    
    # 查找电池选项生成部分并替换为从API获取
    old_battery_options = "    // 电池选项（完整数据集：1-124号）\n    const cellOptions = ref([])\n    // 生成所有电池选项\n    for (let i = 1; i <= 124; i++) {\n      cellOptions.value.push({\n        key: i,\n        label: `电池组 #${i}`\n      })\n    }"
    
    new_battery_options = "    // 电池选项（从API获取）\n    const cellOptions = ref([])\n    \n    // 从API加载电池列表\n    const loadBatteryList = async () => {\n      try {\n        const response = await axios.get(`${API_BASE_URL}/batteries`)\n        if (response.data.success) {\n          cellOptions.value = response.data.data.map(battery => ({\n            key: battery.battery_id,\n            label: `电池组 #${battery.battery_id} (${battery.dataset_type})`\n          }))\n        }\n      } catch (error) {\n        console.error('加载电池列表失败:', error)\n        // 如果API失败，使用默认列表\n        for (let i = 1; i <= 124; i++) {\n          cellOptions.value.push({\n            key: i,\n            label: `电池组 #${i}`\n          })\n        }\n      }\n    }"
    
    content = content.replace(old_battery_options, new_battery_options)
    
    # 更新默认选中电池\n    const selectedCells = ref([85, 100, 124])\n    
    content = content.replace("    const selectedCells = ref([85, 100, 124])", 
                             "    const selectedCells = ref([])  // 从API加载后设置默认值")
    
    # 更新onMounted函数以加载电池列表
    old_on_mounted = "    onMounted(() => {\n      initCharts()\n      window.addEventListener('resize', resizeHandler)\n    })"
    
    new_on_mounted = "    onMounted(async () => {\n      await loadBatteryList()\n      // 设置默认选中电池\n      selectedCells.value = [85, 100, 124]\n      initCharts()\n      window.addEventListener('resize', resizeHandler)\n    })"
    
    content = content.replace(old_on_mounted, new_on_mounted)
    
    # 写回文件
    with open('frontend/src/views/TrainPlatform.vue', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ TrainPlatform.vue已更新，连接到后端API")

if __name__ == "__main__":
    update_train_platform()