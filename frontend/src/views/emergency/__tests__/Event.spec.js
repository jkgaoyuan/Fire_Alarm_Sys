/**
 * 应急事件列表页（3.5-F1 / FR-030 / FR-031）
 *
 * 覆盖：列表渲染、筛选查询、详情抽屉、报告导出（含权限控制）
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import EventList from '../Event.vue'
import { findButton, mountOptions, overlayStub, visibleButtonTexts } from '@/views/device/__tests__/mount'

vi.mock('@/api/emergency', () => ({
  getEmergencyEvents: vi.fn(),
  getEventDetail: vi.fn(),
  getEventTimelines: vi.fn().mockResolvedValue({ data: [] }),
  addTimelineNode: vi.fn(),
  deleteTimelineNode: vi.fn(),
  exportEventReport: vi.fn(),
  getNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markNotificationsAsRead: vi.fn(),
}))

vi.mock('@/api/organization', () => ({
  getOrganizationTree: vi.fn().mockResolvedValue({ data: [] }),
}))

import { getEmergencyEvents, exportEventReport } from '@/api/emergency'

const ALL_PERMS = ['emergency:view', 'emergency:timeline', 'emergency:resolve', 'emergency:close', 'emergency:export']

function event(id, overrides = {}) {
  return {
    id,
    event_no: `EV-20260910-${String(id).padStart(3, '0')}`,
    alarm_id: 100 + id,
    status: 'processing',
    confirmed_by: 'admin',
    created_at: '2026-09-10T10:00:00',
    resolved_at: null,
    ...overrides,
  }
}

async function mountEvent(permissions = ALL_PERMS) {
  const options = mountOptions(permissions)
  options.global.stubs = { ...options.global.stubs, ElDrawer: overlayStub() }
  const wrapper = mount(EventList, options)
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  // jsdom 未实现 createObjectURL，导出下载需要打桩
  window.URL.createObjectURL = vi.fn(() => 'blob:mock-url')
  window.URL.revokeObjectURL = vi.fn()
  getEmergencyEvents.mockResolvedValue({
    data: { items: [event(1), event(2, { status: 'resolved', resolved_at: '2026-09-10T10:30:00' })], total: 2 },
  })
})

describe('应急事件列表（3.5-F1）', () => {
  it('T6-1: 渲染事件表格并展示编号 / 状态 / 关联报警', async () => {
    const wrapper = await mountEvent()

    expect(getEmergencyEvents).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 20 })
    )
    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(rows).toHaveLength(2)

    // 事件编号与状态标签
    expect(rows[0].text()).toContain('EV-20260910-001')
    expect(rows[0].text()).toContain('处理中')
    expect(rows[1].text()).toContain('已解决')
  })

  it('T6-2: 状态筛选把所选值透传给查询接口', async () => {
    const wrapper = await mountEvent()

    // 直接修改 filters.status 触发查询（与 UI 交互一致）
    wrapper.vm.filters.status = 'resolved'
    await findButton(wrapper, '查询').trigger('click')
    await flushPromises()

    expect(getEmergencyEvents).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'resolved', page: 1 })
    )
  })

  it('T6-3: 点击详情打开抽屉并渲染时间轴组件', async () => {
    const wrapper = await mountEvent()

    await findButton(wrapper.findAll('.el-table__body tbody tr')[0], '详情').trigger('click')
    await flushPromises()

    // overlayStub 内联渲染抽屉内容：基础信息 + 只读时间轴
    const drawer = wrapper.find('.overlay-stub')
    expect(drawer.exists()).toBe(true)
    expect(drawer.text()).toContain('EV-20260910-001')
    expect(drawer.find('.timeline-editor').exists()).toBe(true)
  })

  it('T6-4: 无导出权限时报告按钮被隐藏', async () => {
    getEmergencyEvents.mockResolvedValue({ data: { items: [event(1)], total: 1 } })
    const wrapper = await mountEvent(['emergency:view'])

    const texts = visibleButtonTexts(wrapper.findAll('.el-table__body tbody tr')[0])
    expect(texts).toEqual(['详情'])
    expect(texts).not.toContain('报告')
  })

  it('T6-5: 导出报告调用接口并触发浏览器下载（FR-030）', async () => {
    const blob = new Blob(['<html>report</html>'], { type: 'text/html' })
    exportEventReport.mockResolvedValue(blob)
    const wrapper = await mountEvent()

    await findButton(wrapper.findAll('.el-table__body tbody tr')[0], '报告').trigger('click')
    await flushPromises()

    expect(exportEventReport).toHaveBeenCalledWith(1)
    expect(window.URL.createObjectURL).toHaveBeenCalledWith(blob)
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
  })
})
