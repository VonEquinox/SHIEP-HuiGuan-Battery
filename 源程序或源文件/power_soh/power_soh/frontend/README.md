# 储能电池寿命预测算法训练平台前端

## 项目介绍

这是一个基于 Vue 3 和 Element Plus 构建的储能电池寿命预测算法训练平台前端应用。该平台提供以下功能：

- **算法训练平台**：支持 Baseline、BiLSTM、DeepHPM 三种算法模型的训练
- **模型管理**：模型版本管理、保存、加载功能
- **算法测试平台**：电池寿命预测、RUL/PCL 预测曲线展示
- **结果分析**：多种评估指标对比分析

## 技术栈

- Vue 3
- Element Plus UI 组件库
- ECharts 数据可视化
- Vite 构建工具
- Pinia 状态管理

## 功能特性

### 算法训练平台
- 集成三种预测算法模型：Baseline、BiLSTM、DeepHPM
- 支持算法参数灵活配置：网络结构、训练超参数、优化器选择
- 一站式训练流程：数据集自动划分、训练过程实时监控
- 多维度性能评估：RMSPE、MSE、R² 等核心评估指标

### 模型管理
- 模型版本管理
- 训练日志记录
- 模型加载、保存、删除功能

### 算法测试平台
- 电池寿命预测功能
- RUL 和 PCL 预测曲线生成
- 与实际退化曲线对比分析
- 支持预测结果导出

## 安装与运行

1. 安装 Node.js (推荐版本 16.x 或更高)

2. 安装项目依赖
```bash
npm install
```

3. 启动开发服务器
```bash
npm run dev
```

4. 构建生产版本
```bash
npm run build
```

## 项目结构

```
src/
├── components/     # 公共组件
├── views/         # 页面视图
├── api/           # API 接口
├── utils/         # 工具函数
├── assets/        # 静态资源
├── router/        # 路由配置
├── store/         # 状态管理
├── App.vue        # 根组件
└── main.js        # 入口文件
```

## 浏览器支持

- Chrome 67+
- Firefox 62+
- Safari 11+
- Edge 79+

## 开发指南

1. 确保安装了最新版本的 Node.js
2. 运行 `npm install` 安装依赖
3. 运行 `npm run dev` 启动开发服务器
4. 访问 `http://localhost:3000` 查看应用

## 许可证

MIT License