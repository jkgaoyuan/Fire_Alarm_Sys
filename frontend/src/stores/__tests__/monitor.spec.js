import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useMonitorStore, sortAlarms, compareAlarms } from '../monitor'

vi.mock('@/api/monitor', () => ({
  createWsTicket: vi.fn().mockResolvedValue({ data: { ticket: 'tk' } }),
  getDashboard: vi.fn(),
  getRecentAlarms: vi.fn(),
}))

vi.mock('@/services/alarmNotifier', () => ({
  alarmNotifier: {
    muted: false,
    notify: vi.fn().mockResolvedValue({ sound: true, notification: true }),
    silence: vi.fn(),
    stopAll: vi.fn(),
    setMuted: vi.fn((value) => value),
  },
}))

vi.mock('@/utils/websocket', () => ({
  RealtimeClient: vi.fn().mockImplementation((options) => ({
    options,
    connect: vi.fn(),
    close: vi.fn(),
    resetResyncPoint: vi.fn(),
  })),
}))

import { createWsTicket, getDashboard, getRecentAlarms } from '@/api/monitor'
import { alarmNotifier } from '@/services/alarmNotifier'

function alarm(id, overrides = {}) {
  return {
    alarm_id: id,
    device_id: id + 100,
    device_code: `DEV-${id}`,
    device_name: `设备 ${id}`,
    org_id: 5,
    alarm_type: 'fault',
    alarm_level: 'major',
    status: 'pending',
    created_at: `2026-09-09T10:00:${String(id).padStart(2, '0')}+08:00`,
    is_drill: false,
    silenced: false,
    ...overrides,
  }
}

async function flush(turns = 6) {
  for (let i = 0; i < turns; i += 1) await Promise.resolve()
}

describe('monitor store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    getDashboard.mockResolvedValue({ data: { total: 7, pending_fire: 1 } })
    getRecentAlarms.mockResolvedValue({ data: [] })
    alarmNotifier.muted = false
  })

  it('分发帧：新报警入列并鸣响、设备状态打补丁、消音不改状态', async () => {
    const store = useMonitorStore()

    store.handleFrame({ type: 'alarm_new', data: alarm(1) })
    expect(store.alarms).toHaveLength(1)
    expect(alarmNotifier.notify).toHaveBeenCalledTimes(1)

    store.handleFrame({ type: 'alarm_new', data: alarm(2, { alarm_type: 'fire' }) })
    expect(store.pendingFireCount).toBe(1)

    // 重复帧（补发）按 alarm_id 合并，不再追加
    store.handleFrame({ type: 'alarm_new', data: alarm(1, { status: 'confirmed' }) })
    expect(store.alarms).toHaveLength(2)
    expect(store.alarms.find((a) => a.alarm_id === 1).status).toBe('confirmed')
    expect(alarmNotifier.silence).toHaveBeenCalledWith(1)

    store.handleFrame({
      type: 'device_status',
      data: { device_id: 101, status: 'offline', org_id: 5 },
    })
    expect(store.devicePatches[101]).toEqual({ status: 'offline' })

    // 地图点位着色只看仍未收敛的报警
    expect([...store.activeAlarmDeviceIds]).toEqual([102])

    store.handleFrame({ type: 'alarm_silenced', data: { alarm_id: 2, org_id: 5 } })
    const silenced = store.alarms.find((a) => a.alarm_id === 2)
    expect(silenced.silenced).toBe(true)
    expect(silenced.status).toBe('pending')
    expect(alarmNotifier.silence).toHaveBeenCalledWith(2)

    // 演练报警不鸣响（FR-045 隔离）
    store.handleFrame({ type: 'alarm_new', data: alarm(9, { is_drill: true }) })
    expect(alarmNotifier.notify).toHaveBeenCalledTimes(2)

    expect(store.lastFrameAt).toBeTruthy()
  })

  it('未确认火警始终置顶，其余按报警时间倒序', () => {
    const store = useMonitorStore()
    store.handleFrame({ type: 'alarm_new', data: alarm(1, { alarm_type: 'pre_fire' }) })
    store.handleFrame({ type: 'alarm_new', data: alarm(2, { alarm_type: 'fire' }) })
    store.handleFrame({ type: 'alarm_new', data: alarm(3, { alarm_type: 'fault' }) })

    expect(store.visibleAlarms.map((a) => a.alarm_id)).toEqual([2, 3, 1])

    // 火警确认后让位给按时间倒序的普通排序
    store.handleFrame({ type: 'alarm_new', data: alarm(2, { status: 'confirmed' }) })
    expect(store.visibleAlarms.map((a) => a.alarm_id)).toEqual([3, 2, 1])

    const stale = alarm(4, { created_at: '2026-09-01T10:00:00+08:00' })
    const fresh = alarm(5, { created_at: '2026-09-09T23:00:00+08:00' })
    expect(sortAlarms([stale, fresh]).map((a) => a.alarm_id)).toEqual([5, 4])
    // 时间戳无法解析的报警视为最旧，排在末尾
    expect(compareAlarms(stale, { ...stale, created_at: 'not-a-date' })).toBeLessThan(0)
  })

  it('resync_required 时清空增量并全量刷新', async () => {
    const store = useMonitorStore()
    await store.bootstrap()
    const client = store.connect()
    store.handleFrame({ type: 'alarm_new', data: alarm(1) })
    store.handleFrame({ type: 'device_status', data: { device_id: 101, status: 'fault' } })
    getRecentAlarms.mockResolvedValue({ data: [alarm(7)] })

    store.handleFrame({ type: 'resync_required' })
    await flush()

    expect(client.resetResyncPoint).toHaveBeenCalled()
    expect(alarmNotifier.stopAll).toHaveBeenCalled()
    expect(getDashboard).toHaveBeenCalledTimes(2)
    expect(getRecentAlarms).toHaveBeenCalledTimes(2)
    expect(store.alarms.map((a) => a.alarm_id)).toEqual([7])
    expect(store.devicePatches).toEqual({})
    expect(store.resyncCount).toBe(1)
    store.disconnect()
  })

  it('静音态与连接质量状态由 store 统一持有', async () => {
    const store = useMonitorStore()
    expect(store.muted).toBe(false)

    expect(store.toggleMute()).toBe(true)
    expect(alarmNotifier.setMuted).toHaveBeenCalledWith(true)
    expect(store.muted).toBe(true)

    store.setMuted(false)
    expect(store.muted).toBe(false)

    const client = store.connect()
    expect(store.connection).toBe('idle')
    store.handleState('open')
    expect(store.connected).toBe(true)
    store.handleState('reconnecting', { attempt: 3, delay: 8000 })
    expect(store.connected).toBe(false)
    expect(store.reconnectAttempt).toBe(3)
    expect(client.options.fetchTicket).toBe(createWsTicket)

    // 重复 connect 不建立第二条连接
    expect(store.connect()).toBe(client)
    store.disconnect()
    expect(client.close).toHaveBeenCalled()
    expect(store.connection).toBe('closed')
  })
})
