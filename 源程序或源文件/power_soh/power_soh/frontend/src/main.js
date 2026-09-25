import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'

// 创建应用实例
const app = createApp(App)

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 使用插件
app.use(createPinia())
app.use(router)
app.use(ElementPlus)

// 挂载应用
app.mount('#app')

// 添加错误处理
app.config.errorHandler = (err, instance, info) => {
  console.error('Vue错误:', err)
  console.error('错误信息:', info)
  console.error('组件实例:', instance)
}

// 全局错误处理
window.addEventListener('error', (event) => {
  console.error('全局错误:', event.error)
})

window.addEventListener('unhandledrejection', (event) => {
  console.error('未处理的Promise拒绝:', event.reason)
})
