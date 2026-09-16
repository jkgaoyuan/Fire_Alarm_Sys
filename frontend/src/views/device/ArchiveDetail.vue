<template>
  <el-drawer
    :model-value="modelValue"
    title="设备详情"
    size="720px"
    @update:model-value="emit('update:modelValue', $event)"
    @open="loadAll"
  >
    <div v-loading="loading">
      <template v-if="device">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="设备编码">{{ device.device_code }}</el-descriptions-item>
          <el-descriptions-item label="设备名称">{{ device.device_name }}</el-descriptions-item>
          <el-descriptions-item label="设备类型">
            {{ device.type_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="安装区域">
            {{ device.org_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="当前状态">
            <el-tag :type="deviceStatusType(device.status)">
              {{ deviceStatusLabel(device.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="维护周期">
            {{ device.maintain_cycle != null ? `${device.maintain_cycle} 天` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="厂商">{{ device.manufacturer || '-' }}</el-descriptions-item>
          <el-descriptions-item label="品牌/型号">
            {{ [device.brand, device.model].filter(Boolean).join(' / ') || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="安装日期">{{ device.install_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="质保到期">
            {{ device.warranty_expire_date || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="平面图坐标">
            {{ formatCoordinate(device) }}
          </el-descriptions-item>
          <el-descriptions-item label="建档人">
            {{ device.creator_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="扩展属性" :span="2">
            <span v-if="attributeEntries.length === 0" class="text-muted">无</span>
            <el-tag
              v-for="item in attributeEntries"
              :key="item.key"
              type="info"
              class="attribute-tag"
            >
              {{ item.label }}：{{ item.value }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="device.remark" label="备注" :span="2">
            {{ device.remark }}
          </el-descriptions-item>
        </el-descriptions>

        <el-tabs v-model="activeTab" class="history-tabs">
          <!-- 三个历史视图（全部 / 巡检 / 维修）共用同一段时间轴渲染，
               差别只是 visibleHistory 按 activeTab 过滤。

               `lazy` 是必须的：el-tab-pane **默认不懒渲染**，三个页签会各渲染一份
               完整时间轴（实测 DOM 里条目数是数据的 3 倍）。加上它后未访问过的页签
               不渲染，既省一遍 DOM，也让「历史记录页签共几条」这类断言能落在真实数量上。 -->
          <el-tab-pane
            v-for="tab in historyTabs"
            :key="tab.name"
            :label="tab.label"
            :name="tab.name"
            lazy
          >
            <el-timeline v-if="visibleHistory.length > 0">
              <el-timeline-item
                v-for="(item, index) in visibleHistory"
                :key="index"
                :timestamp="formatTime(item.created_at)"
                :type="timelineType(item.category)"
                placement="top"
              >
                <div class="history-title">{{ item.title }}</div>
                <div v-if="item.detail" class="history-detail">{{ item.detail }}</div>
                <div v-if="item.operator" class="history-operator">操作人：{{ item.operator }}</div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else :description="tab.empty" />
          </el-tab-pane>

          <el-tab-pane label="状态轨迹" name="trajectory">
            <DeviceTrajectory v-if="activeTab === 'trajectory'" :device-id="deviceId" />
          </el-tab-pane>
        </el-tabs>
      </template>
      <el-empty v-else description="设备不存在或已被删除" />
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getDevice, getDeviceHistory } from '@/api/device'
import { deviceStatusLabel, deviceStatusType, resolveAttributeFields } from '@/utils/device'
import DeviceTrajectory from './DeviceTrajectory.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  deviceId: { type: Number, default: null },
  deviceTypes: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const device = ref(null)
const history = ref(null)
const activeTab = ref('all')

// 三个历史视图共用同一段时间轴渲染，只是按类别过滤。
// 巡检/维修此前是「模块尚未上线」的占位页签（数据源由后端 `unavailable_sources` 告知）；
// 3.4 / 3.7 已交付、后端已把两类记录聚合进时间轴，占位机制随之移除。
const historyTabs = [
  { name: 'all', label: '历史记录', empty: '该设备暂无历史记录' },
  { name: 'inspection', label: '巡检记录', empty: '该设备暂无巡检记录' },
  { name: 'repair', label: '维修记录', empty: '该设备暂无维修记录' },
]

const visibleHistory = computed(() => {
  const items = history.value?.items || []
  if (activeTab.value === 'all') return items
  return items.filter((item) => item.category === activeTab.value)
})

const attributeEntries = computed(() => {
  if (!device.value) return []
  const type = props.deviceTypes.find((item) => item.id === device.value.type_id)
  const labels = Object.fromEntries(
    resolveAttributeFields(type?.attribute_schema).map((field) => [field.key, field.label])
  )
  return Object.entries(device.value.attributes || {})
    .filter(([, value]) => value !== null && value !== '')
    .map(([key, value]) => ({ key, label: labels[key] || key, value }))
})

function formatTime(value) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 19)
}

function formatCoordinate(item) {
  if (item.map_x == null && item.map_y == null) return '-'
  return `(${item.map_x ?? '-'}, ${item.map_y ?? '-'})`
}

// 按类别分色。此前是「`status_change` 之外一律 `success`」—— 于是**火警在时间轴上
// 渲染成绿色**，与「火警」的语义相反，属既存配色错误，随本次接入一并修正。
const TIMELINE_TYPES = {
  status_change: 'primary',
  alarm: 'danger',
  inspection: 'success',
  repair: 'warning',
}

function timelineType(category) {
  return TIMELINE_TYPES[category] || 'primary'
}

async function loadAll() {
  if (!props.deviceId) return
  loading.value = true
  device.value = null
  history.value = null
  activeTab.value = 'all'
  try {
    const [detail, historyRes] = await Promise.all([
      getDevice(props.deviceId),
      getDeviceHistory(props.deviceId, { limit: 200 }),
    ])
    device.value = detail.data
    history.value = historyRes.data
  } catch (err) {
    ElMessage.error(err.message || '加载设备详情失败')
  } finally {
    loading.value = false
  }
}

/**
 * `deviceId` 变化必须重新取数 —— 只挂抽屉的 `@open` 是不够的。
 *
 * **必须 `immediate: true`**，这条是主场景：`Archive.vue` 监听 `route.query.detail`
 * 时带 `{ immediate: true }`，在 **setup 阶段同步**就把 `detailVisible` 置为 true，
 * 于是 `el-drawer` **第一次渲染时就已经是打开状态**，不存在「关→开」跳变，
 * `@open` **永不触发** → `loadAll()` 从不执行 → `device` 停在 null →
 * 渲染出 v-else 的「设备不存在或已被删除」，而设备其实存在、**请求压根没发出去**。
 * 「大屏电子地图点击设备 → 进设备详情 → 提示设备不存在」走的正是这条路径。
 *
 * 另一条场景：`/device/archive?detail=1` → `?detail=2` 是**同一条路由换 query**，
 * Vue 复用组件不重新挂载，抽屉一直开着 → `open` 同样不触发。
 *
 * 抽屉关着时不预加载（等 `@open`），避免白发一次请求。
 * 两种路径合计只加载一次：已在打开态时本 watch 单独生效（无 open 事件），
 * 关闭态时 `@open` 单独生效（本 watch 被守卫挡下）。
 */
watch(
  () => props.deviceId,
  () => {
    if (props.modelValue) loadAll()
  },
  { immediate: true }
)
</script>

<style lang="scss" scoped>
.history-tabs {
  margin-top: 20px;
}

.history-title {
  font-weight: 600;
}

.history-detail,
.history-operator {
  color: #909399;
  font-size: 13px;
  margin-top: 4px;
}

.attribute-tag {
  margin-right: 6px;
}

.text-muted {
  color: #909399;
}
</style>
