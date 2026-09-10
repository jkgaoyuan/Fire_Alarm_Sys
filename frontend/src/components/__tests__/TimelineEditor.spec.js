/**
 * 处置时间轴编辑器（3.5-F3 / FR-028）
 *
 * 覆盖：只读渲染、编辑模式、节点增删、空状态
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import TimelineEditor from '../TimelineEditor.vue'
import { findButton, overlayStub } from '@/views/device/__tests__/mount'

vi.mock('@/api/emergency', () => ({
  getEventTimelines: vi.fn(),
  addTimelineNode: vi.fn(),
  deleteTimelineNode: vi.fn(),
}))

import { getEventTimelines, addTimelineNode, deleteTimelineNode } from '@/api/emergency'

function node(id, overrides = {}) {
  return {
    id,
    node_type: 'alarm_occurred',
    remark: null,
    user_id: 1,
    attachments: [],
    created_at: '2026-09-10T10:00:00',
    ...overrides,
  }
}

function mountEditor(props = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(TimelineEditor, {
    props: { eventId: 1, readOnly: true, ...props },
    global: {
      plugins: [pinia, ElementPlus],
      stubs: { ElDialog: overlayStub() },
    },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  getEventTimelines.mockResolvedValue({ data: [] })
})

describe('时间轴编辑器（3.5-F3 / FR-028）', () => {
  it('T8-1: 只读模式按时间轴渲染节点与节点名称', async () => {
    getEventTimelines.mockResolvedValue({
      data: [node(1), node(2, { node_type: 'manual_confirm', remark: '值班员现场核实' })],
    })
    const wrapper = mountEditor({ readOnly: true })
    await flushPromises()

    expect(wrapper.find('.read-only-mode').exists()).toBe(true)
    const items = wrapper.findAll('.el-timeline-item')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('报警发生')
    expect(items[1].text()).toContain('人工确认')
    expect(items[1].text()).toContain('值班员现场核实')
  })

  it('T8-2: 编辑模式提供添加节点入口', async () => {
    const wrapper = mountEditor({ readOnly: false })
    await flushPromises()

    expect(wrapper.find('.edit-mode').exists()).toBe(true)
    expect(findButton(wrapper, '添加节点')).toBeDefined()
  })

  it('T8-3: 无节点时展示空状态', async () => {
    getEventTimelines.mockResolvedValue({ data: [] })
    const wrapper = mountEditor()
    await flushPromises()

    expect(wrapper.find('.el-empty').exists()).toBe(true)
  })

  it('T8-4: 提交新增节点会携带节点类型与备注', async () => {
    addTimelineNode.mockResolvedValue({ data: {} })
    getEventTimelines.mockResolvedValue({ data: [] })
    const wrapper = mountEditor({ readOnly: false })
    await flushPromises()

    await findButton(wrapper, '添加节点').trigger('click')
    await flushPromises()

    // overlayStub 内联渲染弹窗内容：选择节点类型 + 填写备注后提交
    const dialog = wrapper.find('.overlay-stub')
    expect(dialog.exists()).toBe(true)

    wrapper.vm.nodeForm.node_type = 'evacuation_started'
    wrapper.vm.nodeForm.remark = '三层人员已疏散'
    await flushPromises()

    await findButton(dialog, '提交').trigger('click')
    await flushPromises()

    expect(addTimelineNode).toHaveBeenCalledWith(1, {
      node_type: 'evacuation_started',
      remark: '三层人员已疏散',
    })
  })

  it('T8-5: 节点类型未选择时提交被拦截', async () => {
    const wrapper = mountEditor({ readOnly: false })
    await flushPromises()

    await findButton(wrapper, '添加节点').trigger('click')
    await flushPromises()

    wrapper.vm.nodeForm.node_type = null
    await findButton(wrapper.find('.overlay-stub'), '提交').trigger('click')
    await flushPromises()

    expect(addTimelineNode).not.toHaveBeenCalled()
  })

  it('T8-6: 删除节点调用删除接口并刷新列表', async () => {
    deleteTimelineNode.mockResolvedValue({})
    getEventTimelines.mockResolvedValue({ data: [node(5, { node_type: 'fire_controlled' })] })
    const wrapper = mountEditor({ readOnly: false })
    await flushPromises()

    await findButton(wrapper, '删除').trigger('click')
    await flushPromises()

    expect(deleteTimelineNode).toHaveBeenCalledWith(5)
    // 删除后会重新加载时间轴
    expect(getEventTimelines).toHaveBeenCalledTimes(2)
  })
})
