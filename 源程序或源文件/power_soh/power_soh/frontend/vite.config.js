import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    open: true,
    allowedHosts: true, // 核心修改：允许所有外部域名（如cpolar/ngrok）访问，解决403报错
    // 代理配置（可选，如果后端支持CORS可以不用）
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        secure: false,
        // rewrite: (path) => path.replace(/^\/api/, '') // 如果后端不需要/api前缀
      }
    }
  },
})