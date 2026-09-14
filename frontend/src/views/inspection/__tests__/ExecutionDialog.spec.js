/**
 * 执行巡检弹窗（ExecutionDialog）
 *
 * 覆盖 2026-09-14 实测缺陷：**维保员登录后点「执行巡检」看不到任何设备，无法提交**。
 *
 * 根因不在这个组件本身，而在它取的数：原先调的是全量 `GET /devices`，
 * 那个端点套通用数据权限，`data_scope='self'` 锚 `devices.created_by`（录入人），
 * 而设备都是管理员录的 → 维保员拿到空表，且 `code 200 / message success`、**不报错**。
 * 现改为 `GET /inspection-tasks/{id}/devices`（按计划范围取「应检设备」）。
 *
 * T1 是这次事故的回归钉子：**只要有人把它改回 `getDevices` 就必须红**。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import ExecutionDialog from '../ExecutionDialog.vue'
import { mountOptions, overlayStub } from '@/views/device/__tests__/mount'

vi.mock('@/api/inspection', () => ({
  getTaskDevices: vi.fn(),
  submitInspectionRecord: vi.fn(),
}))

// 故意把 getDevices 也 mock 出来：这样若组件回退成调用它，
// 断言里能明确指出「调错了端点」，而不是报一个语焉不详的 undefined
vi.mock('@/api/device', () => ({
  getDevices: vi.fn(),
}))

import { getTaskDevices, submitInspectionRecord } from '@/api/inspection'
import { getDevices } from '@/api/device'

const SAMPLE_DEVICES = {
  code: 200,
  message: 'success',
  data: {
    items: [
      {
        id: 1,
        device_code: 'DEV-SMK-001',
        device_name: '1F大厅烟感A01',
        type_id: 11,
        type_name: '烟感探测器',
        org_id: 21,
        org_name: '总部大楼',
        status: 'normal',
      },
      {
        id: 2,
        device_code: 'DEV-SMK-002',
        device_name: '1F大厅烟感A02',
        type_id: 11,
        type_name: '烟感探测器',
        org_id: 21,
        org_name: '总部大楼',
        status: 'normal',
      },
    ],
    total: 2,
    page: 1,
    page_size: 100,
  },
}

function mountDialog(props = {}) {
  const options = mountOptions(['inspection:execute'])
  options.global.stubs = {
    ...options.global.stubs,
    ElDialog: overlayStub(),
  }
  return mount(ExecutionDialog, {
    props: { taskId: 44, modelValue: true, ...props },
    global: options.global,
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  getTaskDevices.mockResolvedValue(SAMPLE_DEVICES)
  getDevices.mockResolvedValue({ data: { items: [], total: 0 } })
  submitInspectionRecord.mockResolvedValue({ code: 200, message: 'success' })
})

describe('ExecutionDialog.vue', () => {
  it('T1: 必须调「应检设备」端点，不能回退到全量 /devices', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    expect(getTaskDevices).toHaveBeenCalledWith(44, expect.objectContaining({ page: 1 }))
    expect(
      getDevices,
      '调回了全量 /devices —— 该端点套通用数据权限（self 锚 created_by），' +
        '维保员的设备列表会恒为空且不报错'
    ).not.toHaveBeenCalled()
  })

  it('T2: 应检设备渲染进表格', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    expect(wrapper.vm.allDevices).toHaveLength(2)
    expect(wrapper.text()).toContain('1F大厅烟感A01')
    expect(wrapper.text()).toContain('烟感探测器')
  })

  it('T3: 设备为空时给出说明文案，而不是一张看不出所以然的空表格', async () => {
    getTaskDevices.mockResolvedValue({
      code: 200,
      data: { items: [], total: 0, page: 1, page_size: 100 },
    })
    const wrapper = mountDialog()
    await flushPromises()

    // Element Plus 的 el-table 把 empty-text 渲染到 .el-table__empty-text
    expect(wrapper.find('.el-table__empty-text').exists()).toBe(true)
    expect(wrapper.find('.el-table__empty-text').text()).toContain('该任务范围内没有可检设备')
  })

  it('T4: 未选设备时提交应被拦下**并给出提示**', async () => {
    // ⚠️ 只断言 `submitInspectionRecord` 没被调用是不够的 —— 这条断言在
    // **删掉守卫之后依然成立**：代码会继续往下走到 `currentSelectedDevice.value.id`，
    // 在读 null 的属性时抛 TypeError，被外层 catch 吞掉，于是「没提交」依然为真。
    // 断言「没发生某事」时，必须确认拦住它的是被测的那段代码，而不是后面某个意外异常。
    // 这里钉住守卫独有的可观测副作用：一条提示。
    const warnSpy = vi.spyOn(ElMessage, 'warning')
    const wrapper = mountDialog()
    await flushPromises()

    await wrapper.vm.handleSubmit()
    await flushPromises()

    expect(warnSpy).toHaveBeenCalledWith('请先选择设备')
    expect(submitInspectionRecord).not.toHaveBeenCalled()

    warnSpy.mockRestore()
  })

  it('T5: 选中设备后提交带上 task_id 与该设备 id', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    wrapper.vm.handleDeviceSelect(wrapper.vm.allDevices[0])
    await wrapper.vm.handleSubmit()
    await flushPromises()

    expect(submitInspectionRecord).toHaveBeenCalledWith(
      44,
      expect.objectContaining({ task_id: 44, device_id: 1 })
    )
  })

  it('T6: taskId 变化后重新拉取（换任务不能沿用上一个任务的设备）', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    expect(getTaskDevices).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ taskId: 45 })
    await flushPromises()

    expect(getTaskDevices).toHaveBeenCalledTimes(2)
    expect(getTaskDevices).toHaveBeenLastCalledWith(45, expect.anything())
  })
})
