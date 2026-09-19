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
  resolveEvent: vi.fn(),
  closeEvent: vi.fn(),
  getNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markNotificationsAsRead: vi.fn(),
}))

// MessageBox 渲染在组件树之外，替换为可控 mock，其余导出保持原样
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessageBox: {
      ...actual.ElMessageBox,
      prompt: vi.fn(),
      confirm: vi.fn(),
    },
  }
})

vi.mock('@/api/organization', () => ({
  getOrganizationTree: vi.fn().mockResolvedValue({ data: [] }),
}))

import { ElMessageBox } from 'element-plus'
import { getEmergencyEvents, exportEventReport, resolveEvent, closeEvent } from '@/api/emergency'

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
  // 填后端真实信封（含 message），空壳 { code: 200 } 会让成功分支的文案断言失效
  resolveEvent.mockResolvedValue({ code: 200, message: '处置完成', data: event(1, { status: 'resolved' }) })
  closeEvent.mockResolvedValue({ code: 200, message: '事件已关闭', data: event(1, { status: 'closed' }) })
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

  it('T6-6: 处置完成弹窗填写总结后调用 resolveEvent 并刷新列表', async () => {
    const wrapper = await mountEvent()
    ElMessageBox.prompt.mockResolvedValue({ value: '已扑灭，无人员伤亡' })

    await findButton(wrapper.findAll('.el-table__body tbody tr')[0], '处置完成').trigger('click')
    await flushPromises()

    expect(resolveEvent).toHaveBeenCalledWith(1, '已扑灭，无人员伤亡')
    // 处置后必须重新拉列表，否则状态仍显示「处理中」
    expect(getEmergencyEvents).toHaveBeenCalledTimes(2)
  })

  it('T6-7: 取消处置完成弹窗时不调用接口', async () => {
    const wrapper = await mountEvent()
    ElMessageBox.prompt.mockRejectedValue('cancel')

    await findButton(wrapper.findAll('.el-table__body tbody tr')[0], '处置完成').trigger('click')
    await flushPromises()

    // 先钉住弹窗确实被呼出过，否则「没调接口」可能是因为按钮压根没绑定
    expect(ElMessageBox.prompt).toHaveBeenCalledTimes(1)
    expect(resolveEvent).not.toHaveBeenCalled()
  })

  it('T6-8: 关闭事件二次确认后调用 closeEvent；取消则不调用', async () => {
    const wrapper = await mountEvent()
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    const row = () => wrapper.findAll('.el-table__body tbody tr')[0]

    await findButton(row(), '关闭事件').trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(confirmSpy.mock.calls[0][0]).toContain('关闭')
    expect(closeEvent).toHaveBeenCalledWith(1)
    expect(getEmergencyEvents).toHaveBeenCalledTimes(2)

    closeEvent.mockClear()
    confirmSpy.mockRejectedValue('cancel')
    await findButton(row(), '关闭事件').trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalledTimes(2)
    expect(closeEvent).not.toHaveBeenCalled()
  })

  it('T6-9: 无 emergency:resolve / emergency:close 权限时两个执行按钮均隐藏', async () => {
    const wrapper = await mountEvent(['emergency:view', 'emergency:export'])

    const texts = visibleButtonTexts(wrapper.findAll('.el-table__body tbody tr')[0])
    expect(texts).toEqual(['详情', '报告'])
  })

  it('T6-10: 已关闭的事件不再提供处置完成与关闭事件', async () => {
    getEmergencyEvents.mockResolvedValue({
      data: { items: [event(1, { status: 'closed' })], total: 1 },
    })
    const wrapper = await mountEvent()

    const texts = visibleButtonTexts(wrapper.findAll('.el-table__body tbody tr')[0])
    expect(texts).toEqual(['详情', '报告'])
    // 「报告」仍在，证明隐藏的是状态条件而不是整列没渲染
    expect(texts).toContain('报告')
  })

  it('T6-11: 详情内时间轴按 emergency:timeline 权限决定可编辑或只读', async () => {
    const editable = await mountEvent()
    await findButton(editable.findAll('.el-table__body tbody tr')[0], '详情').trigger('click')
    await flushPromises()
    expect(findButton(editable.find('.overlay-stub'), '添加节点')).toBeTruthy()

    const readOnly = await mountEvent(['emergency:view'])
    await findButton(readOnly.findAll('.el-table__body tbody tr')[0], '详情').trigger('click')
    await flushPromises()
    expect(readOnly.find('.overlay-stub').find('.timeline-editor').exists()).toBe(true)
    expect(findButton(readOnly.find('.overlay-stub'), '添加节点')).toBeFalsy()
  })
})
