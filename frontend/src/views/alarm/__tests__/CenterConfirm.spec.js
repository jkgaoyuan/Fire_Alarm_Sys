import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Center from '../Center.vue'
import {
  findButton,
  mountOptions,
  visibleDialogStub,
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

import { confirmAlarm, getAlarms } from '@/api/alarm'

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
    created_at: `2026-09-19T10:00:${String(id).padStart(2, '0')}`,
    is_drill: false,
    ...overrides,
  }
}

/**
 * 演练告警默认被 `filters.include_drill` 过滤掉（matchesFilters），
 * 所以必须先打开「含演练」开关——用户实测能碰到这条告警，正是走了这条路。
 */
async function mountCenterWithAlarm(row) {
  getAlarms.mockResolvedValue({ data: { items: [row], total: 1, page: 1, page_size: 20 } })
  const options = mountOptions(ALL_PERMS)
  options.global.stubs = { ...options.global.stubs, ElDialog: visibleDialogStub() }
  const wrapper = mount(Center, options)
  await flushPromises()

  const switchInput = wrapper.find('.el-switch input[type="checkbox"]')
  await switchInput.setValue(true)
  await flushPromises()
  return wrapper
}

async function openConfirmDialog(wrapper) {
  const row = wrapper.findAll('.el-table__body tbody tr')[0]
  await findButton(row, '确认').trigger('click')
  await flushPromises()
  return wrapper.find('.el-dialog-open')
}

function radioByText(dialog, text) {
  return dialog.findAll('.el-radio').find((item) => item.text().includes(text))
}

describe('报警确认弹窗与演练告警（3.5-B2 / 3.8 演练隔离）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('演练告警：禁用「现场属实」，并说明不会创建应急事件', async () => {
    const wrapper = await mountCenterWithAlarm(alarm(9, { is_drill: true }))
    const dialog = await openConfirmDialog(wrapper)

    expect(dialog.exists()).toBe(true)
    expect(radioByText(dialog, '现场属实').classes()).toContain('is-disabled')
    expect(dialog.text()).toContain('演练告警')
    expect(dialog.text()).not.toContain('将自动创建')
  })

  it('演练告警：弹窗默认不选「现场属实」，避免默认提交一个必被后端拒绝的结论', async () => {
    const wrapper = await mountCenterWithAlarm(alarm(9, { is_drill: true }))
    const dialog = await openConfirmDialog(wrapper)

    // 误报分支才会渲染「误报原因」，据此判断默认停在误报上
    expect(dialog.text()).toContain('误报原因')
  })

  it('演练告警：误报路径仍可提交（否则演练告警永远卡在待确认）', async () => {
    const wrapper = await mountCenterWithAlarm(alarm(9, { is_drill: true }))
    const dialog = await openConfirmDialog(wrapper)

    // 直接驱动 v-model：el-select 的下拉是 teleport 到 body 的，在 jsdom 里点不到
    const reasonSelect = dialog.findComponent({ name: 'ElSelect' })
    expect(reasonSelect.exists()).toBe(true)
    reasonSelect.vm.$emit('update:modelValue', '演练触发')
    await flushPromises()

    await findButton(dialog, '提交确认').trigger('click')
    await flushPromises()

    expect(confirmAlarm).toHaveBeenCalled()
    expect(confirmAlarm.mock.calls[0][1].confirm_result).toBe('false_alarm')
  })

  it('非演练告警：仍可选「现场属实」且保留自动创建事件的承诺文案', async () => {
    const wrapper = await mountCenterWithAlarm(alarm(1))
    const dialog = await openConfirmDialog(wrapper)

    expect(radioByText(dialog, '现场属实').classes()).not.toContain('is-disabled')
    expect(dialog.text()).toContain('将自动创建')
  })
})
