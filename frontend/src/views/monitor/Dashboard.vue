<template>
  <div class="page-container monitor-dashboard">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar__left">
          <span class="toolbar__title">实时监控大屏</span>
          <el-cascader
            v-model="orgId"
            :options="orgOptions"
            :props="cascaderProps"
            placeholder="全部区域"
            clearable
            style="width: 220px"
            @change="handleOrgChange"
          />
          <el-tag :type="connectionMeta.type" size="small" effect="dark">{{ connectionMeta.label }}</el-tag>
          <span v-if="store.reconnectAttempt > 0" class="toolbar__dim">
            第 {{ store.reconnectAttempt }} 次重连
          </span>
          <span v-if="store.resyncCount > 0" class="toolbar__dim">
            补发溢出，已全量刷新 {{ store.resyncCount }} 次
          </span>
        </div>
        <div class="toolbar__right">
          <el-button :type="store.muted ? 'warning' : 'primary'" plain @click="handleMuteToggle">
            <el-icon><component :is="store.muted ? MuteNotification : Bell" /></el-icon>
            {{ store.muted ? '已静音（点击取消）' : '全部静音' }}
          </el-button>
          <PermissionButton permission="monitor:config" @click="settingVisible = true">
            地图设置
          </PermissionButton>
          <el-button @click="handleRefresh">刷新</el-button>
        </div>
      </div>
    </el-card>

    <div class="stat-grid">
      <el-card
        v-for="card in statCards"
        :key="card.key"
        shadow="never"
        class="stat-card"
        :class="{ 'stat-card--active': card.highlight }"
      >
        <div class="stat-card__label">{{ card.label }}</div>
        <div class="stat-card__value" :style="{ color: card.color }">{{ card.value }}</div>
        <div class="stat-card__extra">{{ card.extra }}</div>
      </el-card>

      <el-card shadow="never" class="stat-card stat-card--distribution">
        <div class="stat-card__label">状态分布</div>
        <div class="distribution">
          <div v-for="item in distribution" :key="item.value" class="distribution__row">
            <span class="distribution__name">
              <span class="alarm-dot" :class="`alarm-dot--${item.value}`" />{{ item.label }}
            </span>
            <span class="distribution__value">{{ item.count }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <el-card shadow="never" class="content-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane name="alarms">
          <template #label>
            <span class="tab-label">
              实时报警
              <el-badge v-if="store.pendingFireCount" :value="store.pendingFireCount" type="danger" />
            </span>
          </template>
          <AlarmList
            :alarms="store.visibleAlarms"
            :loading="store.loading"
            @silence="handleSilence"
            @handle="gotoCenter"
            @focus-device="gotoDevice"
          />
        </el-tab-pane>

        <el-tab-pane label="电子地图" name="map">
          <MapView
            v-if="activeTab === 'map'"
            :org-id="orgId"
            @open-setting="settingVisible = true"
            @focus-device="gotoDevice"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <MapSetting
      v-model="settingVisible"
      :org-id="settingTargetOrgId"
      @success="handleMapSaved"
    />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, MuteNotification } from '@element-plus/icons-vue'
import AlarmList from './components/AlarmList.vue'
import MapView from './MapView.vue'
import MapSetting from './MapSetting.vue'
import PermissionButton from '@/components/PermissionButton.vue'
import { getOrganizationTree } from '@/api/organization'
import { silenceAlarm } from '@/api/alarm'
import { useMonitorStore } from '@/stores/monitor'
import { alarmNotifier } from '@/services/alarmNotifier'
import { DEVICE_STATUS_OPTIONS, deviceStatusLabel, stripEmptyChildren } from '@/utils/device'
import { alarmIdOf } from '@/utils/alarm'

const CONNECTION_META = {
  idle: { type: 'info', label: '未连接' },
  connecting: { type: 'primary', label: '连接中' },
  open: { type: 'success', label: '实时连接' },
  reconnecting: { type: 'warning', label: '重连中' },
  closed: { type: 'info', label: '已断开' },
}

const cascaderProps = {
  label: 'org_name',
  value: 'id',
  children: 'children',
  checkStrictly: true,
  emitPath: false,
}

const router = useRouter()
const store = useMonitorStore()

const orgId = ref(null)
const activeTab = ref('alarms')
const settingVisible = ref(false)
const orgOptions = ref([])

const dashboard = computed(() => store.dashboard || {})
const connectionMeta = computed(
  () => CONNECTION_META[store.connection] || CONNECTION_META.idle
)
/** 未指定区域时按当前用户可见范围配置根节点楼层 */
const settingTargetOrgId = computed(() => orgId.value || store.orgId || null)

const statCards = computed(() => {
  const d = dashboard.value
  return [
    {
      key: 'total',
      label: '设备总数',
      value: d.total ?? 0,
      extra: `离线 ${d.offline ?? 0} · 已退役 ${d.retired ?? 0}`,
      color: '#303133',
    },
    {
      key: 'online',
      label: '在线设备',
      value: d.online ?? 0,
      extra: `状态正常 ${d.normal ?? 0}`,
      color: '#67c23a',
    },
    {
      key: 'alarm',
      label: '报警设备',
      value: d.alarm ?? 0,
      extra: `待确认 ${d.pending_alarm ?? 0} · 火警 ${d.pending_fire ?? 0}`,
      color: '#f56c6c',
      highlight: (d.pending_fire ?? 0) > 0,
    },
    {
      key: 'fault',
      label: '故障设备',
      value: d.fault ?? 0,
      extra: `屏蔽 ${d.shield ?? 0}`,
      color: '#e6a23c',
    },
  ]
})

const distribution = computed(() => {
  const counts = dashboard.value.status_counts || {}
  return DEVICE_STATUS_OPTIONS.map((item) => ({
    value: item.value,
    label: item.label,
    count: counts[item.value] || 0,
  }))
})

onMounted(async () => {
  await store.bootstrap()
  store.acquire()
  loadOrgTree()
  // 浏览器自动播放策略要求首个用户手势内解锁音频，否则报警音会被静默拦截
  window.addEventListener('click', unlockAudio, { once: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('click', unlockAudio)
  store.release()
})

function unlockAudio() {
  alarmNotifier.unlock()
}

async function loadOrgTree() {
  try {
    const res = await getOrganizationTree()
    orgOptions.value = stripEmptyChildren(res.data || [])
  } catch (err) {
    ElMessage.error(err.message || '加载组织架构失败')
  }
}

async function handleOrgChange(value) {
  try {
    await store.selectOrg(value || null)
  } catch (err) {
    ElMessage.error(err.message || '加载监控数据失败')
  }
}

async function handleRefresh() {
  try {
    await store.bootstrap()
    ElMessage.success('已刷新')
  } catch (err) {
    ElMessage.error(err.message || '刷新失败')
  }
}

async function handleMuteToggle() {
  const next = !store.muted
  store.setMuted(next)
  if (!next) {
    // 取消静音是一次明确的交互，此时申请桌面通知权限才会弹出系统授权框
    alarmNotifier.unlock()
    const granted = await alarmNotifier.ensureNotificationPermission()
    if (!granted && globalThis.Notification?.permission === 'denied') {
      ElMessage.warning('桌面通知权限被拒绝，报警将只以提示音与页面动画呈现')
    }
  }
  ElMessage.success(next ? '已静音本页报警提示音' : '已取消静音')
}

async function handleSilence(alarm) {
  try {
    await silenceAlarm(alarmIdOf(alarm))
    // 广播 alarm_silenced 会回填状态；WS 不可用时兜底本地刷新
    store.markSilenced({ alarm_id: alarmIdOf(alarm) })
    ElMessage.success('已消音，报警状态保持不变')
  } catch (err) {
    ElMessage.error(err.message || '消音失败')
  }
}

function gotoCenter(alarm) {
  router.push({ path: '/alarm/center', query: { alarm_id: alarmIdOf(alarm) || undefined } })
}

function gotoDevice(alarmOrPoint) {
  const deviceId = alarmOrPoint.device_id ?? alarmOrPoint.id
  if (!deviceId) return
  router.push({ path: '/device/archive', query: { detail: deviceId } })
}

async function handleMapSaved() {
  if (activeTab.value === 'map') {
    orgId.value = orgId.value
    await store.bootstrap()
  }
}
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20px;
}

.toolbar-card {
  margin-bottom: 16px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;

  &__left,
  &__right {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  &__title {
    font-size: 16px;
    font-weight: 600;
  }

  &__dim {
    color: #909399;
    font-size: 12px;
  }
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.stat-card {
  &--active {
    animation: alarm-breathe 1.6s ease-in-out infinite;
  }

  &__label {
    color: #909399;
    font-size: 13px;
  }

  &__value {
    font-size: 30px;
    font-weight: 600;
    line-height: 1.4;
  }

  &__extra {
    color: #909399;
    font-size: 12px;
  }
}

.distribution {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 2px 12px;
  font-size: 12px;

  &__row {
    display: flex;
    justify-content: space-between;
  }

  &__name {
    color: #606266;
  }
}

.content-card {
  :deep(.el-tabs__header) {
    margin-bottom: 0;
  }
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
</style>
