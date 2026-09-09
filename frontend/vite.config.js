import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

const isTest = process.env.VITEST !== undefined

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    !isTest && AutoImport({
      resolvers: [ElementPlusResolver()],
    }),
    !isTest && Components({
      resolvers: [ElementPlusResolver()],
    }),
  ].filter(Boolean),
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: `@use "@/styles/variables.scss" as *;`,
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // 实时推送（FR-013）：不升级协议时握手会退回 404
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
      // 平面图等上传件由后端 /static 提供
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['src/test-setup.js'],
    include: ['src/**/*.{test,spec}.{js,jsx,ts,tsx}'],
    server: {
      // element-plus 的 ESM 产物由 Node 直接加载时，async-validator 的 CJS 默认导出会被解析成
      // 命名空间对象，表单校验静默失效；交给 Vite 转译才有 interop
      deps: { inline: ['element-plus'] },
    },
  },
})
