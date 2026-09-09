import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Dashboard from '../Dashboard.vue'
import { useMonitorStore } from '@/stores/monitor'

const { push } = vi.hoisted(() => ({ push: vi.fn() }))

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal()
  // stores/permission 会导入真实 router，只能覆盖 useRouter
  return { ...actual, useRouter: () => ({ push }) }
})

vi.mock('@/api/monitor', () => ({
  createWsTicket: vi.fn().mockResolvedValue({ data: { ticket: 'tk' } }),
  getDashboard: vi.fn(),
  getRecentAlarms: vi.fn(),
  getMapMeta: vi.fn().mockResolvedValue({ data: null }),
  getMapDevices: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }),
}))

vi.mock('@/api/organization', () => ({
  getOrganizationTree: vi.fn().mockResolvedValue({ data: [] }),
}))

vi.mock('@/api/alarm', () => ({
  silenceAlarm: vi.fn().mockResolvedValue({ data: {} }),
}))

vi.mock('@/services/alarmNotifier', () => ({
  alarmNotifier: {
    muted: false,
    notify: vi.fn().mockResolvedValue({ sound: true, notification: true }),
    silence: vi.fn(),
    stopAll: vi.fn(),
    setMuted: vi.fn((value) => !!value),
    unlock: vi.fn(),
    ensureNotificationPermission: vi.fn().mockResolvedValue(false),
  },
}))

vi.mock('@/utils/websocket', () => ({
  RealtimeClient: vi.fn().mockImplementation(() => ({
    connect: vi.fn(),
    close: vi.fn(),
    resetResyncPoint: vi.fn(),
  })),
}))

import { getDashboard, getRecentAlarms } from '@/api/monitor'
import { silenceAlarm } from '@/api/alarm'
import { alarmNotifier } from '@/services/alarmNotifier'

import { mountOptions, visibleButtonTexts } from '@/views/device/__tests__/mount'

function alarm(id, overrides = {}) {
  return {
    alarm_id: id,
    device_id: 100 + id,
    device_code: `DEV-${id}`,
    device_name: `设备 ${id}`,
    org_id: 5,
    org_name: '1F',
    alarm_type: 'fault',
    alarm_level: 'minor',
    status: 'pending',
    created_at: `2026-09-09T10:00:${String(id).padStart(2, '0')}`,
    is_drill: false,
    silenced: false,
    ...overrides,
  }
}

async function mountDashboard(permissions = []) {
  const options = mountOptions(permissions)
  // Leaflet 与平面图设置抽屉不在本次断言范围内
  options.global.stubs = { ...options.global.stubs, MapView: true, MapSetting: true }
  const wrapper = mount(Dashboard, options)
  await flushPromises()
  return wrapper
}

describe('监控大屏（F-13 / FR-014）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getDashboard.mockResolvedValue({
      data: { total: 12, online: 10, alarm: 2, fault: 1, pending_fire: 1, pending_alarm: 2 },
    })
    // 后端按时间倒序返回，未确认火警排在末位，置顶只能由前端保证
    getRecentAlarms.mockResolvedValue({
      data: [
        alarm(1, { alarm_type: 'fault' }),
        alarm(2, { alarm_type: 'shield', status: 'resolved' }),
        alarm(3, { alarm_type: 'fire', alarm_level: 'critical' }),
        alarm(4, { alarm_type: 'fire', status: 'confirmed' }),
        alarm(5, { is_drill: true }),
      ],
    })
  })

  it('未确认火警置顶渲染，呼吸灯只作用于未消音火警', async () => {
    const wrapper = await mountDashboard(['monitor:view', 'alarm:silence', 'device:view'])
    const store = useMonitorStore()

    const rows = wrapper.findAll('.alarm-row')
    // 演练报警不占大屏席位（FR-045 隔离）
    expect(rows).toHaveLength(4)
    expect(wrapper.text()).not.toContain('设备 5')
    expect(rows.map((row) => row.text())).toEqual([
      expect.stringContaining('设备 3'),
      expect.stringContaining('设备 4'),
      expect.stringContaining('设备 2'),
      expect.stringContaining('设备 1'),
    ])

    // 待确认火警：红色配色 + 呼吸动画
    expect(rows[0].classes()).toContain('alarm-row--fire')
    expect(rows[0].classes()).toContain('alarm-row--breathing')
    // 已确认火警让位但仍保留火警配色；已解决行置灰
    expect(rows[1].classes()).toContain('alarm-row--fire')
    expect(rows[1].classes()).not.toContain('alarm-row--breathing')
    expect(rows[2].classes()).toContain('alarm-row--resolved')
    expect(rows[3].classes()).toContain('alarm-row--fault')
    expect(rows[3].classes()).not.toContain('alarm-row--breathing')

    expect(store.pendingFireCount).toBe(1)
    expect(wrapper.find('.stat-card--active').exists()).toBe(true)

    // 消音只停闪烁与鸣响，报警行仍在位（FR-016.1）
    store.markSilenced({ alarm_id: 3 })
    await flushPromises()
    const afterSilence = wrapper.findAll('.alarm-row')
    expect(afterSilence).toHaveLength(4)
    expect(afterSilence[0].classes()).not.toContain('alarm-row--breathing')
    expect(afterSilence[0].text()).toContain('已消音')
    expect(alarmNotifier.silence).toHaveBeenCalledWith(3)
  })

  it('静音与消音操作按权限呈现并落到接口', async () => {
    const wrapper = await mountDashboard(['monitor:view'])

    expect(visibleButtonTexts(wrapper.findAll('.alarm-row')[0])).toEqual(['处置'])
    expect(visibleButtonTexts(wrapper)).not.toContain('地图设置')

    await wrapper.find('.toolbar__right button').trigger('click')
    await flushPromises()
    expect(useMonitorStore().muted).toBe(true)
    expect(alarmNotifier.setMuted).toHaveBeenCalledWith(true)

    const full = await mountDashboard([
      'monitor:view',
      'monitor:config',
      'alarm:silence',
      'device:view',
    ])
    expect(visibleButtonTexts(full.findAll('.alarm-row')[0])).toEqual(['消音', '处置', '设备'])
    expect(visibleButtonTexts(full)).toContain('地图设置')

    // 处置跳转报警中心并带上 alarm_id，由中心页打开处置弹窗（F-16）
    await full.findAll('.alarm-row')[0].findAll('button')[1].trigger('click')
    expect(push).toHaveBeenCalledWith({ path: '/alarm/center', query: { alarm_id: 3 } })

    // 消音成功后报警不消失，只停鸣响（FR-016.1）
    await full.findAll('.alarm-row')[0].findAll('button')[0].trigger('click')
    await flushPromises()
    expect(silenceAlarm).toHaveBeenCalledWith(3)
    expect(useMonitorStore().alarms.find((item) => item.alarm_id === 3).silenced).toBe(true)
  })
})
