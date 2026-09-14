/**
 * 任务统计信息弹窗（StatsDialog）
 *
 * 覆盖 2026-09-14 两个缺陷：
 *
 * **1. 弹窗打不开**（与 RecordViewer / PlanDetail 同根因）：`v-model` 绑在局部
 * `ref(false)` 上，从不读 `props.modelValue` → 局部 ref 无人置 true → 永远不弹。
 *
 * **2. 内容是编造的**：修好打开之后，原来的实现写死
 * `plan_name: '示例计划'`、`task_date: new Date()`、`status: 'pending'`，
 * 而 `recordsCount / abnormalCount / completionRate` 三个 ref **从未被赋值**，
 * 恒为 0 —— 弹窗会一本正经地显示「示例计划 / 0个 / 0次」，**看着像真数据**。
 * 这正是本项目反复栽的坑（维修统计页四项指标恒为 0、已记录数恒为 0）。
 * 现改为：任务事实全部取自行数据，异常次数取后端 `result=abnormal` 的 total。
 *
 * 「完成率」已移除：任务级没有真实分母（计划级完成率在计划详情里），
 * 凭空算一个比不显示更糟。用一个假的 0% 顶替是原实现的错误做法。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import StatsDialog from '../StatsDialog.vue'
import { mountOptions, visibleDialogStub } from '@/views/device/__tests__/mount'

vi.mock('@/api/inspection', () => ({
  getInspectionRecords: vi.fn(),
}))

import { getInspectionRecords } from '@/api/inspection'

const SAMPLE_TASK = {
  id: 44,
  plan_id: 7,
  task_date: '2026-09-14',
  status: 'doing',
  completed_at: null,
  // ⚠️ 计划名**故意不含「每日」**：早先这个样本叫「每日巡检-总部大楼」，
  // 于是断言 `text()` 含「每日」在周期类型读错字段时**依然通过**——
  // 命中的是计划名里的「每日」。做变异测试时才发现是假绿。
  // 计划名与周期标签不得互为子串，断言一律走 descValue 精确定位。
  plan_name: '总部大楼-A栋例行巡检',
  plan_cycle_type: 'daily',
  responsible_user_id: 3,
  responsible_user_name: '张三',
  records_count: 12,
}

/**
 * 按 label 取 el-descriptions 里该行的值。
 *
 * 不能用 `wrapper.text()` 断言字段内容：整块文本里任何一处出现目标子串都会通过，
 * 字段读错、读成别的字段，甚至只显示 '-' 都可能被别处的文字掩盖。
 * el-descriptions 的 label / content 是相邻兄弟节点，取 nextElementSibling 最稳。
 */
function descValue(wrapper, label) {
  const cell = wrapper
    .findAll('.el-descriptions__label')
    .find((c) => c.text() === label)
  if (!cell) return null
  return cell.element.nextElementSibling?.textContent?.trim() ?? null
}

function mountStats(props = {}) {
  const options = mountOptions(['inspection:stat'])
  options.global.stubs = {
    ...options.global.stubs,
    ElDialog: visibleDialogStub(),
  }
  return mount(StatsDialog, {
    props: { task: SAMPLE_TASK, modelValue: false, ...props },
    global: options.global,
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  getInspectionRecords.mockResolvedValue({
    code: 200,
    data: { items: [], total: 3, page: 1, page_size: 1 },
  })
})

describe('StatsDialog.vue', () => {
  it('T1: modelValue=true 时弹窗必须真的打开', async () => {
    const wrapper = mountStats({ modelValue: true })
    await flushPromises()

    expect(wrapper.find('.el-dialog-open').exists()).toBe(true)
  })

  it('T2: 展示的是任务行里的真实数据，不是占位假数据', async () => {
    const wrapper = mountStats({ modelValue: true })
    await flushPromises()

    expect(descValue(wrapper, '所属计划')).toBe('总部大楼-A栋例行巡检')
    expect(descValue(wrapper, '任务日期')).toBe('2026-09-14')
    expect(descValue(wrapper, '责任人')).toBe('张三')
    // 原实现写死的占位值不得再出现
    expect(wrapper.text()).not.toContain('示例计划')
  })

  it('T3: 已记录数取 records_count（后端真实计数）', async () => {
    const wrapper = mountStats({ modelValue: true })
    await flushPromises()

    expect(descValue(wrapper, '已记录设备数')).toBe('12 个')
  })

  it('T9: 已记录数与异常/正常次数三者必须自洽', async () => {
    // 12 = 异常 3 + 正常 9。三个数字都渲染出来并核对，避免「各显示各的」——
    // 原实现正是三个恒 0 的 ref 各显示各的，看着很协调，全是假的。
    const wrapper = mountStats({ modelValue: true })
    await flushPromises()

    const abnormal = Number(descValue(wrapper, '其中异常').replace(/[^\d]/g, ''))
    const normal = Number(descValue(wrapper, '其中正常').replace(/[^\d]/g, ''))
    expect(abnormal).toBe(3)
    expect(normal).toBe(9)
    expect(abnormal + normal).toBe(SAMPLE_TASK.records_count)
  })

  it('T4: 异常次数走后端 result=abnormal 的 total，而不是恒 0 的本地 ref', async () => {
    const wrapper = mountStats({ modelValue: true })
    await flushPromises()

    expect(getInspectionRecords).toHaveBeenCalledWith(
      expect.objectContaining({ task_id: 44, result: 'abnormal' })
    )
    expect(wrapper.vm.abnormalCount).toBe(3)
  })

  it('T5: 正常次数 = 已记录数 - 异常次数', async () => {
    const wrapper = mountStats({ modelValue: true })
    await flushPromises()

    expect(wrapper.vm.normalCount).toBe(9)
  })

  it('T6: 周期类型读 plan_cycle_type（后端真实字段名），渲染成中文', async () => {
    // 原实现读 taskData.cycle_type —— 后端返回的是 plan_cycle_type，
    // 读错字段名会静默拿到 undefined → 显示 '-'（本项目已多次出现同类问题）。
    // 精确定位到「周期类型」那一行，不能用 text() 模糊匹配（见 SAMPLE_TASK 注释）。
    const wrapper = mountStats({ modelValue: true })
    await flushPromises()

    expect(descValue(wrapper, '周期类型')).toBe('每日')
  })

  it('T7: 关闭时 emit update:modelValue(false)', async () => {
    const wrapper = mountStats({ modelValue: true })
    await flushPromises()

    await wrapper.find('.el-dialog-close').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('T8: 统计接口失败不得把弹窗搞崩，异常次数降级但页面仍在', async () => {
    getInspectionRecords.mockRejectedValue(new Error('boom'))
    const wrapper = mountStats({ modelValue: true })
    await flushPromises()

    expect(wrapper.find('.el-dialog-open').exists()).toBe(true)
    expect(wrapper.vm.abnormalCount).toBe(0)
  })
})
