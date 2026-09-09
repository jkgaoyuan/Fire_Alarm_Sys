/**
 * 实时监控 store（F-12 / FR-013~FR-014）
 *
 * 承接 WebSocket 帧分发：大屏统计、报警列表置顶排序、静音态与连接质量。
 * 视图只读这里的派生状态，不各自开连接，避免多标签页重复推送。
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { createWsTicket, getDashboard, getRecentAlarms } from '@/api/monitor'
import { RealtimeClient } from '@/utils/websocket'
import { alarmNotifier } from '@/services/alarmNotifier'

/** 大屏报警列表长度，与后端 /monitor/alarms/recent 默认值一致 */
export const RECENT_LIMIT = 20

/** 高频 device_status 帧下的统计刷新节流，避免每张上报都打一次聚合查询 */
const DASHBOARD_REFRESH_DEBOUNCE_MS = 2000

function createdValue(alarm) {
  const time = Date.parse(alarm.created_at || '')
  return Number.isNaN(time) ? 0 : time
}

/** 置顶规则（计划 5.1）：未确认火警优先，其余按报警时间倒序 */
export function compareAlarms(a, b) {
  const aTop = a.status === 'pending' && a.alarm_type === 'fire' ? 0 : 1
  const bTop = b.status === 'pending' && b.alarm_type === 'fire' ? 0 : 1
  if (aTop !== bTop) return aTop - bTop
  return createdValue(b) - createdValue(a)
}

export function sortAlarms(list) {
  return [...list].sort(compareAlarms)
}

/** 报警状态收敛后不再占用呼吸灯（confirmed/false_alarm/resolved） */
function isUnresolved(alarm) {
  return alarm.status === 'pending' || alarm.status === 'processing'
}

export const useMonitorStore = defineStore('monitor', () => {
  const dashboard = ref(null)
  const alarms = ref([])
  const connection = ref('idle')
  const lastFrameAt = ref(null)
  const reconnectAttempt = ref(0)
  const resyncCount = ref(0)
  const muted = ref(alarmNotifier.muted)
  const orgId = ref(null)
  const loading = ref(false)

  /** device_id → 实时状态补丁（device_status 帧 / 复位）；报警标记由 alarms 派生 */
  const devicePatches = ref({})

  let client = null
  let refreshTimer = null
  /** 正在使用实时推送的页面数；页面切换时卸载/挂载先后顺序不定，必须计数 */
  let consumers = 0

  const pendingFireCount = computed(
    () => alarms.value.filter((a) => a.status === 'pending' && a.alarm_type === 'fire').length
  )
  const visibleAlarms = computed(() => sortAlarms(alarms.value))
  const connected = computed(() => connection.value === 'open')
  /** 地图点位着色：TopN 列表内仍有未收敛报警的设备 */
  const activeAlarmDeviceIds = computed(
    () => new Set(alarms.value.filter(isUnresolved).map((a) => a.device_id))
  )

  async function refreshDashboard() {
    const res = await getDashboard(orgId.value ? { org_id: orgId.value } : {})
    dashboard.value = res.data
  }

  async function refreshAlarms() {
    const params = { limit: RECENT_LIMIT }
    if (orgId.value) params.org_id = orgId.value
    const res = await getRecentAlarms(params)
    alarms.value = sortAlarms(res.data || [])
  }

  /** 首次进入大屏：先取快照再接 WS，否则重连补发会把历史帧当新报警播放提示音 */
  async function bootstrap() {
    loading.value = true
    try {
      await Promise.all([refreshDashboard(), refreshAlarms()])
    } finally {
      loading.value = false
    }
  }

  function connect() {
    if (client) return client
    client = new RealtimeClient({
      fetchTicket: createWsTicket,
      onFrame: handleFrame,
      onState: handleState,
    })
    client.connect()
    return client
  }

  /** 视图挂载时调用；与 release 成对，避免页面互相跳转时把刚建立的连接关掉 */
  function acquire() {
    consumers += 1
    return connect()
  }

  function release() {
    consumers = Math.max(0, consumers - 1)
    if (consumers === 0) disconnect()
  }

  function disconnect() {
    if (client) {
      client.close()
      client = null
    }
    if (refreshTimer) {
      clearTimeout(refreshTimer)
      refreshTimer = null
    }
    alarmNotifier.stopAll()
    connection.value = 'closed'
  }

  function handleState(state, detail) {
    connection.value = state
    if (state === 'open') reconnectAttempt.value = 0
    if (state === 'reconnecting') reconnectAttempt.value = detail.attempt || 0
  }

  function setMuted(value) {
    muted.value = alarmNotifier.setMuted(value)
    return muted.value
  }

  function toggleMute() {
    return setMuted(!muted.value)
  }

  async function selectOrg(nextOrgId) {
    orgId.value = nextOrgId || null
    devicePatches.value = {}
    await bootstrap()
  }

  function scheduleDashboardRefresh() {
    if (refreshTimer) return
    refreshTimer = setTimeout(async () => {
      refreshTimer = null
      try {
        await refreshDashboard()
      } catch {
        // 统计刷新失败等下一帧或用户手动刷新，不打断实时链路
      }
    }, DASHBOARD_REFRESH_DEBOUNCE_MS)
  }

  function handleFrame(frame) {
    if (!frame || !frame.type) return
    lastFrameAt.value = Date.now()
    switch (frame.type) {
      case 'alarm_new':
        upsertAlarm(frame.data, { notify: true })
        scheduleDashboardRefresh()
        break
      case 'alarm_confirmed':
        upsertAlarm(frame.data)
        alarmNotifier.silence(frame.data.alarm_id)
        scheduleDashboardRefresh()
        break
      case 'alarm_reset':
        upsertAlarm(frame.data)
        alarmNotifier.silence(frame.data.alarm_id)
        patchDevice({
          device_id: frame.data.device_id,
          status: 'normal',
        })
        scheduleDashboardRefresh()
        break
      case 'alarm_silenced':
        markSilenced(frame.data)
        break
      case 'device_status':
        patchDevice(frame.data)
        scheduleDashboardRefresh()
        break
      case 'resync_required':
        requestResync()
        break
      default:
        // pong / metrics 只用于连接质量展示
        break
    }
  }

  /** 补发/重复帧按 alarm_id 覆盖，不重复鸣响 */
  function upsertAlarm(payload, { notify = false } = {}) {
    if (!payload || payload.alarm_id == null) return
    const index = alarms.value.findIndex((a) => a.alarm_id === payload.alarm_id)
    if (index >= 0) {
      const merged = { ...alarms.value[index], ...payload }
      alarms.value[index] = merged
      if (!isUnresolved(merged)) alarmNotifier.silence(payload.alarm_id)
      else if (notify && !merged.is_drill) alarmNotifier.notify(merged)
      return
    }
    alarms.value.push(payload)
    if (notify && isUnresolved(payload) && !payload.is_drill) alarmNotifier.notify(payload)
    if (alarms.value.length > RECENT_LIMIT) {
      alarms.value = sortAlarms(alarms.value).slice(0, RECENT_LIMIT)
    }
  }

  function markSilenced(payload) {
    if (!payload || payload.alarm_id == null) return
    const target = alarms.value.find((a) => a.alarm_id === payload.alarm_id)
    if (target) {
      // 消音只停鸣响与闪烁，status 不变（FR-016.1 报警仍需被看见）
      target.silenced = true
    }
    alarmNotifier.silence(payload.alarm_id)
  }

  function patchDevice(payload) {
    if (!payload || payload.device_id == null || !payload.status) return
    devicePatches.value = {
      ...devicePatches.value,
      [payload.device_id]: { ...devicePatches.value[payload.device_id], status: payload.status },
    }
  }

  /** 服务端补发溢出：丢弃本地增量，走 REST 全量刷新 */
  function requestResync() {
    resyncCount.value += 1
    if (client) client.resetResyncPoint()
    alarms.value = []
    devicePatches.value = {}
    alarmNotifier.stopAll()
    bootstrap()
  }

  return {
    dashboard,
    alarms,
    visibleAlarms,
    devicePatches,
    connection,
    connected,
    lastFrameAt,
    reconnectAttempt,
    resyncCount,
    muted,
    orgId,
    loading,
    pendingFireCount,
    activeAlarmDeviceIds,
    refreshDashboard,
    refreshAlarms,
    bootstrap,
    connect,
    disconnect,
    acquire,
    release,
    handleFrame,
    handleState,
    setMuted,
    toggleMute,
    selectOrg,
    upsertAlarm,
    markSilenced,
    patchDevice,
    requestResync,
  }
})
