#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
更新ResultsAnalysis.vue以连接后端API
"""

def update_results_analysis():
    # 读取原始文件
    with open('frontend/src/views/ResultsAnalysis.vue', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换import部分
    old_import = "import { ref, onMounted, onUnmounted, reactive } from 'vue'\nimport * as echarts from 'echarts'\n\nexport default {"
    
    new_import = "import { ref, onMounted, onUnmounted, reactive } from 'vue'\nimport * as echarts from 'echarts'\nimport axios from 'axios'\n\n// API 基础地址\nconst API_BASE_URL = 'http://localhost:5000/api'\n\nexport default {"
    
    content = content.replace(old_import, new_import)
    
    # 添加API获取数据的函数
    # 找到setup函数开始的地方
    setup_start = "  setup() {\n    // 选择的算法"
    
    new_setup_start = "  setup() {\n    // 选择的算法\n    const selectedAlgorithms = ref(['baseline', 'bilstm', 'deepphm'])\n    \n    // 选择的指标\n    const selectedMetrics = ref(['rmspe', 'mse', 'r2'])\n    \n    // 比较类型\n    const comparisonType = ref('algorithm')\n    \n    // 从API获取结果数据\n    const fetchResultsData = async () => {\n      try {\n        // 获取模型比较结果\n        const response = await axios.get(`${API_BASE_URL}/models/comparison`)\n        if (response.data.success) {\n          // 更新图表数据\n          updatePerformanceChart(response.data.data)\n          updateConvergenceChart(response.data.data)\n          updateRobustnessChart(response.data.data)\n        }\n      } catch (error) {\n        console.error('获取结果数据失败:', error)\n        // 如果API失败，使用模拟数据\n        updatePerformanceChart()\n        updateConvergenceChart()\n        updateRobustnessChart()\n      }\n    }"
    
    content = content.replace(setup_start, new_setup_start)
    
    # 更新onMounted函数
    old_on_mounted = "    onMounted(() => {\n      // 初始化所有图表\n      initPerformanceChart()\n      initConvergenceChart()\n      initRobustnessChart()\n      initPredictionChart()\n    })"
    
    new_on_mounted = "    onMounted(async () => {\n      // 初始化所有图表\n      initPerformanceChart()\n      initConvergenceChart()\n      initRobustnessChart()\n      initPredictionChart()\n      \n      // 从API获取数据\n      await fetchResultsData()\n    })"
    
    content = content.replace(old_on_mounted, new_on_mounted)
    
    # 写回文件
    with open('frontend/src/views/ResultsAnalysis.vue', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ ResultsAnalysis.vue已更新，连接到后端API")

if __name__ == "__main__":
    update_results_analysis()