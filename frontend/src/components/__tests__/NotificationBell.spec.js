/**
 * 通知中心铃铛（3.5-F5 / FR-025 超时升级通知入口）
 *
 * 覆盖：徽章计数、下拉交互、通知内容、已读操作
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import NotificationBell from '../NotificationBell.vue'

vi.mock('@/api/emergency', () => ({
  getNotifications: vi.fn(),
  markNotificationRead: vi.fn().mockResolvedValue({}),
  markNotificationsAsRead: vi.fn().mockResolvedValue({}),
}))

import { getNotifications, markNotificationRead, markNotificationsAsRead } from '@/api/emergency'

function notification(id, overrides = {}) {
  return {
    id,
    title: '报警超时未确认',
    category: 'emergency_escalation',
    alarm_id: 12,
    event_no: null,
    is_read: false,
    created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    ...overrides,
  }
}

function mountBell() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(NotificationBell, {
    global: { plugins: [pinia, ElementPlus] },
    attachTo: document.body,
  })
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  getNotifications.mockResolvedValue({ data: { items: [], total: 0 } })
})

describe('通知铃铛（3.5-F5 / FR-025）', () => {
  it('T5-1: 无未读时徽章隐藏且不渲染红点', async () => {
    const wrapper = mountBell()
    await flushPromises()

    expect(wrapper.find('.notification-bell').exists()).toBe(true)
    expect(wrapper.find('.notification-dot').exists()).toBe(false)
    wrapper.unmount()
  })

  it('T5-2: 有未读时显示红点并在下拉中列出通知', async () => {
    getNotifications.mockResolvedValue({
      data: { items: [notification(1), notification(2, { is_read: true })], total: 2 },
    })
    const wrapper = mountBell()
    await flushPromises()

    // 红点仅由未读触发
    expect(wrapper.find('.notification-dot').exists()).toBe(true)

    // 点击铃铛展开下拉
    await wrapper.find('.notification-bell').trigger('click')
    await flushPromises()

    expect(wrapper.find('.notification-dropdown').isVisible()).toBe(true)
    const items = wrapper.findAll('.notification-item')
    expect(items).toHaveLength(2)
    // 未读项带 unread 标记，已读项没有
    expect(items[0].classes()).toContain('unread')
    expect(items[1].classes()).not.toContain('unread')
    wrapper.unmount()
  })

  it('T5-3: 超时升级通知渲染对应的提示文案', async () => {
    getNotifications.mockResolvedValue({
      data: { items: [notification(3, { category: 'emergency_escalation', alarm_id: 12 })] },
    })
    const wrapper = mountBell()
    await flushPromises()

    await wrapper.find('.notification-bell').trigger('click')
    await flushPromises()

    expect(wrapper.find('.notification-item').text()).toContain('应急升级：报警 #12 超时未确认')
    wrapper.unmount()
  })

  it('T5-4: 点击未读通知会标记已读并刷新列表', async () => {
    getNotifications.mockResolvedValue({ data: { items: [notification(9)], total: 1 } })
    const wrapper = mountBell()
    await flushPromises()

    await wrapper.find('.notification-bell').trigger('click')
    await flushPromises()

    await wrapper.find('.notification-item').trigger('click')
    await flushPromises()

    expect(markNotificationRead).toHaveBeenCalledWith(9)
    expect(getNotifications).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('T5-5: 全部已读按钮调用批量接口', async () => {
    getNotifications.mockResolvedValue({ data: { items: [notification(4)], total: 1 } })
    const wrapper = mountBell()
    await flushPromises()

    await wrapper.find('.notification-bell').trigger('click')
    await flushPromises()

    const markAllBtn = wrapper.findAll('button').find((btn) => btn.text().includes('全部已读'))
    await markAllBtn.trigger('click')
    await flushPromises()

    expect(markNotificationsAsRead).toHaveBeenCalled()
    wrapper.unmount()
  })
})
