/**
 * 巡检记录查看弹窗（RecordViewer）
 *
 * 本文件覆盖 2026-09-14 实测缺陷：任务页点「查看记录」没有任何弹窗。
 *
 * **根因**：组件把 `v-model` 绑在**局部** `const visible = ref(false)` 上，
 * 而父组件传进来的是 `modelValue` prop —— `props.modelValue` 全文件从未被读取。
 * 局部 ref 初值 false，唯一的赋值语句在 `handleClose` 里写 false，
 * **没有任何路径能把它置为 true**，所以弹窗永远打不开。
 * （同病三个文件：RecordViewer / StatsDialog / PlanDetail。见 dialogContract.spec.js 的守卫。）
 *
 * T1 用 `visibleDialogStub()` 而非 `overlayStub()`：后者无条件渲染内容，
 * 会把「压根没打开」这个缺陷盖住（详见 mount.js 里该替身的注释）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import RecordViewer from '../RecordViewer.vue'
import { mountOptions, visibleDialogStub } from '@/views/device/__tests__/mount'

vi.mock('@/api/inspection', () => ({
  getInspectionRecords: vi.fn(),
}))

import { getInspectionRecords } from '@/api/inspection'

const SAMPLE_RECORDS = {
  code: 200,
  message: 'success',
  data: {
    items: [
      {
        id: 1,
        task_id: 44,
        device_id: 1,
        device_code: 'DEV-SMK-001',
        device_name: '1F大厅烟感A01',
        result: 'normal',
        abnormal_desc: null,
        photos: [],
        inspected_by: 3,
        inspected_by_name: '张三',
        inspected_at: '2026-09-14T20:30:34',
      },
    ],
    total: 1,
    page: 1,
    page_size: 100,
  },
}

function mountViewer(props = {}) {
  const options = mountOptions(['inspection:view'])
  options.global.stubs = {
    ...options.global.stubs,
    ElDialog: visibleDialogStub(),
  }
  return mount(RecordViewer, {
    props: { taskId: 44, modelValue: false, ...props },
    global: options.global,
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  getInspectionRecords.mockResolvedValue(SAMPLE_RECORDS)
})

describe('RecordViewer.vue', () => {
  it('T1: modelValue=true 时弹窗必须真的打开', async () => {
    const wrapper = mountViewer({ modelValue: true })
    await flushPromises()

    expect(wrapper.find('.el-dialog-open').exists()).toBe(true)
  })

  it('T2: modelValue=false 时不渲染内容', async () => {
    const wrapper = mountViewer({ modelValue: false })
    await flushPromises()

    expect(wrapper.find('.el-dialog-open').exists()).toBe(false)
  })

  it('T3: 打开时按 task_id 拉取记录并渲染', async () => {
    const wrapper = mountViewer({ modelValue: true })
    await flushPromises()

    expect(getInspectionRecords).toHaveBeenCalledWith(
      expect.objectContaining({ task_id: 44 })
    )
    expect(wrapper.vm.recordList).toHaveLength(1)
  })

  it('T4: 关闭时 emit update:modelValue(false)，父组件的 v-model 才会跟着复位', async () => {
    const wrapper = mountViewer({ modelValue: true })
    await flushPromises()

    await wrapper.find('.el-dialog-close').trigger('click')
    await flushPromises()

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted, '关闭必须回传 update:modelValue，否则父组件状态与界面脱节').toBeDefined()
    expect(emitted.at(-1)).toEqual([false])
  })

  it('T5: 打开后再传 modelValue=false 能关掉（父组件可外部控制）', async () => {
    const wrapper = mountViewer({ modelValue: true })
    await flushPromises()
    expect(wrapper.find('.el-dialog-open').exists()).toBe(true)

    await wrapper.setProps({ modelValue: false })
    await flushPromises()

    expect(wrapper.find('.el-dialog-open').exists()).toBe(false)
  })
})
