import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/api/device', () => ({
  getDevice: vi.fn(),
  getDeviceHistory: vi.fn(),
}))

import { getDevice, getDeviceHistory } from '@/api/device'
import ArchiveDetail from '../ArchiveDetail.vue'
import { overlayOptions, SAMPLE_DEVICE, SAMPLE_TYPES } from './mount'

const HISTORY = {
  device_id: 1,
  device_code: 'DEV-SMK-001',
  total: 2,
  items: [
    {
      category: 'status_change',
      title: '状态变更：正常 → 已退役',
      detail: '设备老化，整机更换',
      operator: 'admin',
      created_at: '2026-09-08T11:20:00',
    },
    {
      category: 'status_change',
      title: '建档：DEV-SMK-001',
      detail: '初始状态：正常',
      operator: 'chief',
      created_at: '2026-03-15T09:00:00',
    },
  ],
  unavailable_sources: ['inspection', 'repair'],
}

async function mountDetail(props = {}) {
  const wrapper = mount(ArchiveDetail, overlayOptions({ deviceTypes: SAMPLE_TYPES, ...props }))
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  return wrapper
}

describe('ArchiveDetail.vue 设备档案详情', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getDevice.mockResolvedValue({ data: SAMPLE_DEVICE })
    getDeviceHistory.mockResolvedValue({ data: HISTORY })
  })

  it('打开时并行加载档案与历史并渲染字段', async () => {
    const wrapper = await mountDetail({ deviceId: SAMPLE_DEVICE.id })

    expect(getDevice).toHaveBeenCalledWith(SAMPLE_DEVICE.id)
    expect(getDeviceHistory).toHaveBeenCalledWith(SAMPLE_DEVICE.id, { limit: 200 })

    const text = wrapper.text()
    expect(text).toContain('DEV-SMK-001')
    expect(text).toContain('1F大厅烟感A01')
    expect(text).toContain('烟感探测器')
    expect(text).toContain('总部大楼')
    expect(text).toContain('正常')
    expect(text).toContain('90 天')
    expect(text).toContain('Honeywell / XLS-PS')
    expect(text).toContain('2025-03-15')
    expect(text).toContain('(120.5, 340.2)')
    expect(text).toContain('chief')
  })

  it('扩展属性按类型 schema 显示中文标签', async () => {
    const wrapper = await mountDetail({ deviceId: 1 })

    expect(wrapper.text()).toContain('灵敏度：高')
    expect(wrapper.text()).toContain('探测面积(㎡)：60')
    expect(wrapper.findAll('.attribute-tag')).toHaveLength(2)
  })

  it('历史记录按时间倒序展示变更内容与操作人', async () => {
    const wrapper = await mountDetail({ deviceId: 1 })

    const entries = wrapper.findAll('.el-timeline-item')
    expect(entries).toHaveLength(2)
    expect(entries[0].text()).toContain('状态变更：正常 → 已退役')
    expect(entries[0].text()).toContain('设备老化，整机更换')
    expect(entries[0].text()).toContain('操作人：admin')
    expect(entries[0].text()).toContain('2026-09-08 11:20:00')
    expect(entries[1].text()).toContain('建档：DEV-SMK-001')
  })

  it('未上线的数据源以占位页签显式告知', async () => {
    const wrapper = await mountDetail({ deviceId: 1 })

    const tabs = wrapper.findAll('.el-tabs__item').map((tab) => tab.text())
    expect(tabs).toEqual(
      expect.arrayContaining(['历史记录', '状态轨迹', '巡检记录', '维修记录'])
    )
    // 报警记录已由 3.3 聚合进时间轴，不再是占位数据源
    expect(tabs).not.toContain('报警记录')

    const inspectionTab = wrapper.findAll('.el-tabs__item').find((tab) => tab.text() === '巡检记录')
    await inspectionTab.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('巡检记录模块尚未上线，暂无数据')
    expect(wrapper.text()).toContain('对应开发计划：3.4 巡检管理')
  })

  it('档案接口失败时显示空态而不是抛错', async () => {
    getDevice.mockRejectedValue(new Error('设备不存在'))
    const wrapper = await mountDetail({ deviceId: 999 })

    expect(wrapper.text()).toContain('设备不存在或已被删除')
    expect(wrapper.find('.el-descriptions').exists()).toBe(false)
  })
})
