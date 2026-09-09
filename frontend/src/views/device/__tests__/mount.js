/**
 * 设备档案视图组件测试共用挂载配置
 *
 * 测试环境下 vite.config 关闭了 AutoImport / Components 插件，
 * 因此需要显式安装 ElementPlus 插件并注册 v-permission 指令。
 */
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h, nextTick, watch } from 'vue'
import { usePermissionStore } from '@/stores/permission'

/** 被测视图涉及的路径；用空组件占位，避免引入生产路由守卫 */
const VIEW_PATHS = [
  '/login',
  '/403',
  '/404',
  '/monitor/dashboard',
  '/monitor/map',
  '/alarm/center',
  '/device/archive',
]

const Blank = { render: () => h('div') }

/**
 * 内存路由；path 用于预置 query，方便断言深链行为。
 * @param {string} [path] 初始完整路径，如 '/alarm/center?alarm_id=3'
 */
export function createTestRouter(path = '/') {
  const router = createRouter({
    history: createMemoryHistory('/'),
    routes: [
      ...VIEW_PATHS.map((item) => ({ path: item, component: Blank })),
      // 内存路由的初始位置是空串，缺 catch-all 会刷一屏 No match 警告
      { path: '/:pathMatch(.*)*', component: Blank },
    ],
  })
  if (path !== '/') router.push(path)
  return router
}

/** 有权限时正常渲染、无权限时隐藏，语义与真实指令一致 */
export const permissionDirective = {
  mounted(el, binding) {
    const store = usePermissionStore()
    const value = binding.value
    const codes = Array.isArray(value) ? value : [value]
    if (!codes.some((code) => store.permissions.includes(code))) {
      el.style.display = 'none'
    }
  },
}

/**
 * @param {string[]} permissions 模拟当前用户权限码
 * @param {string} [path] 初始路由，可带 query，如 '/device/archive?detail=1'
 */
export function mountOptions(permissions = [], path = '/') {
  const pinia = createPinia()
  setActivePinia(pinia)
  usePermissionStore().permissions = permissions
  return {
    global: {
      plugins: [pinia, createTestRouter(path), ElementPlus],
      directives: { permission: permissionDirective },
      stubs: {
        ArchiveForm: true,
        ArchiveImport: true,
        ArchiveDetail: true,
      },
    },
  }
}

/**
 * el-drawer / el-dialog 的内容会 teleport 到 body，而 global.stubs.teleport 会让
 * ElSelect 的下拉 popper 进入无限递归更新，因此改为把浮层组件本身替换成内联渲染的占位组件，
 * 并补发真实浮层打开时才有的 open 事件。
 */
export function overlayStub() {
  return defineComponent({
    inheritAttrs: false,
    props: {
      modelValue: { type: Boolean, default: false },
      title: { type: String, default: '' },
    },
    emits: ['open'],
    setup(props, { emit, slots }) {
      watch(
        () => props.modelValue,
        (visible) => {
          if (visible) nextTick(() => emit('open'))
        }
      )
      return () =>
        h('div', { class: 'overlay-stub' }, [
          h('span', { class: 'overlay-stub__title' }, props.title),
          slots.default?.(),
          slots.footer?.(),
        ])
    },
  })
}

/**
 * @param {Record<string, unknown>} props 组件 props，浮层默认关闭以便触发 open
 */
export function overlayOptions(props = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  usePermissionStore().permissions = []
  return {
    props: { modelValue: false, ...props },
    global: {
      plugins: [pinia, ElementPlus],
      directives: { permission: permissionDirective },
      stubs: { ElDrawer: overlayStub(), ElDialog: overlayStub() },
    },
  }
}

/** 找到文案包含指定文本的按钮 */
export function findButton(wrapper, text) {
  return wrapper.findAll('button').find((btn) => btn.text().includes(text))
}

/** v-permission 通过内联样式隐藏按钮，断言可见性需过滤 display:none */
export function visibleButtonTexts(scope) {
  return scope
    .findAll('button')
    .filter((btn) => btn.attributes('style') !== 'display: none;')
    .map((btn) => btn.text())
}

export const SAMPLE_DEVICE = {
  id: 1,
  device_code: 'DEV-SMK-001',
  device_name: '1F大厅烟感A01',
  type_id: 11,
  type_name: '烟感探测器',
  category: 'detector',
  org_id: 21,
  org_name: '总部大楼',
  manufacturer: '霍尼韦尔',
  brand: 'Honeywell',
  model: 'XLS-PS',
  spec: '光电型',
  install_date: '2025-03-15',
  warranty_expire_date: '2028-03-15',
  maintain_cycle: 90,
  status: 'normal',
  map_x: 120.5,
  map_y: 340.2,
  attributes: { sensitivity: '高', detection_area: 60 },
  remark: null,
  is_deleted: false,
  created_by: 3,
  creator_name: 'chief',
  created_at: '2026-09-08T10:00:00',
  updated_at: '2026-09-08T10:00:00',
}

export const SAMPLE_TYPES = [
  {
    id: 11,
    type_code: 'smoke_detector',
    type_name: '烟感探测器',
    category: 'detector',
    attribute_schema: {
      sensitivity: { label: '灵敏度', type: 'select', options: ['高', '中', '低'] },
      detection_area: { label: '探测面积(㎡)', type: 'number' },
    },
  },
]

export const SAMPLE_ORG_TREE = [
  {
    id: 20,
    parent_id: null,
    org_name: '消防监控中心',
    org_type: 'unit',
    sort_order: 0,
    children: [
      { id: 21, parent_id: 20, org_name: '总部大楼', org_type: 'building', sort_order: 0, children: [] },
    ],
  },
]
