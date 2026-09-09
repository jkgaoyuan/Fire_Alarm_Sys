import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// 报警动效与分级配色跨大屏/报警中心/地图共用，必须全局注册
import './styles/monitor.scss'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import { permission } from './directives/permission'

const app = createApp(App)

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 注册全局权限指令
app.directive('permission', permission)

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

app.mount('#app')
