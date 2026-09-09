import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Center from '../Center.vue'
import {
  findButton,
  mountOptions,
  overlayStub,
  visibleButtonTexts,
} from '@/views/device/__tests__/mount'

vi.mock('@/api/monitor', () => ({
  createWsTicket: vi.fn().mockResolvedValue({ data: { ticket: 'tk' } }),
  getDashboard: vi.fn().mockResolvedValue({ data: {} }),
  getRecentAlarms: vi.fn().mockResolvedValue({ data: [] }),
}))

vi.mock('@/api/organization', () => ({
  getOrganizationTree: vi.fn().mockResolvedValue({ data: [] }),
}))

vi.mock('@/api/alarm', () => ({
  getAlarm: vi.fn(),
  getAlarms: vi.fn(),
  confirmAlarm: vi.fn().mockResolvedValue({ data: {} }),
  resetAlarm: vi.fn().mockResolvedValue({ data: {} }),
  silenceAlarm: vi.fn().mockResolvedValue({ data: {} }),
}))

vi.mock('@/services/alarmNotifier', () => ({
  alarmNotifier: {
    muted: false,
    notify: vi.fn().mockResolvedValue({}),
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

import { getAlarms, resetAlarm } from '@/api/alarm'

const ALL_PERMS = ['alarm:view', 'alarm:confirm', 'alarm:silence', 'alarm:reset', 'device:view']

function alarm(id, overrides = {}) {
  return {
    id,
    device_id: 100 + id,
    device_code: `DEV-${id}`,
    device_name: `设备 ${id}`,
    org_id: 5,
    org_name: '1F',
    alarm_type: 'fire',
    alarm_level: 'critical',
    status: 'pending',
    created_at: `2026-09-09T10:00:${String(id).padStart(2, '0')}`,
    is_drill: false,
    ...overrides,
  }
}

async function mountCenter(permissions = ALL_PERMS) {
  const options = mountOptions(permissions)
  options.global.stubs = { ...options.global.stubs, ElDialog: overlayStub() }
  const wrapper = mount(Center, options)
  await flushPromises()
  return wrapper
}

describe('报警中心（F-16 / FR-016）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getAlarms.mockResolvedValue({
      data: {
        items: [alarm(1), alarm(2, { status: 'processing', alarm_type: 'fault' })],
        total: 2,
        page: 1,
        page_size: 20,
      },
    })
  })

  it('复位必须先勾选"已确认现场物理状态恢复"才可提交', async () => {
    const wrapper = await mountCenter()
    expect(wrapper.findAll('.el-table__body tbody tr')).toHaveLength(2)

    await findButton(wrapper.findAll('.el-table__body tbody tr')[0], '复位').trigger('click')
    const submit = findButton(wrapper, '确认复位')

    // 未勾选：按钮禁用，点击不会发出复位请求
    expect(submit.attributes('disabled')).toBeDefined()
    await submit.trigger('click')
    await flushPromises()
    expect(resetAlarm).not.toHaveBeenCalled()

    // 勾选后即可复位，且显式带上 physical_restored（FR-016.2 人工确认位）
    await wrapper.find('.reset-form input[type="checkbox"]').setValue(true)
    await flushPromises()
    const enabled = findButton(wrapper, '确认复位')
    expect(enabled.attributes('disabled')).toBeUndefined()
    await enabled.trigger('click')
    await flushPromises()
    expect(resetAlarm).toHaveBeenCalledWith(1, { physical_restored: true, remark: undefined })
  })

  it('已解决的报警不再提供消音与复位入口', async () => {
    getAlarms.mockResolvedValue({
      data: {
        items: [
          alarm(3, { status: 'resolved' }),
          alarm(4, { status: 'pending', silenced_at: '2026-09-09T10:05:00' }),
        ],
        total: 2,
      },
    })
    const wrapper = await mountCenter()
    const rows = wrapper.findAll('.el-table__body tbody tr')

    // 与大屏同一套置顶规则：未确认火警排在首行
    // 已消音的待确认火警不再重复提供消音，但仍可确认与复位
    expect(visibleButtonTexts(rows[0])).toEqual(['详情', '确认', '复位', '设备'])
    // 已解决的报警只剩详情与设备跳转
    expect(visibleButtonTexts(rows[1])).toEqual(['详情', '设备'])
  })
})
