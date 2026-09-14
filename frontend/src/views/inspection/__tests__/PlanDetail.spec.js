/**
 * 巡检计划详情弹窗（PlanDetail）
 *
 * 覆盖 2026-09-14 三个缺陷：
 *
 * **1. 弹窗打不开**：与 RecordViewer / StatsDialog 同根因——`v-model` 绑在局部
 * `ref(false)` 上，`props.modelValue` 全文件从未被读取，局部 ref 无人置 true。
 * 这个文件此前**零测试覆盖**：唯一提到它的 `Plan.spec.js:75` 用 `PlanDetail: true`
 * 把整个组件 stub 掉，缺陷完全不可见。
 *
 * **2. 「任务列表」不按计划过滤**：`loadTasks()` 调 `getInspectionTasks({page, page_size})`
 * 从不传 `plan_id`（后端此前也不支持该参数）→ 计划 A 的详情里显示的是**全量任务**。
 *
 * **3. el-tag 的 type 传空串**：`taskStatusType('pending')` 返回 `''`，
 * 会拼出不存在的 class `el-tag--`，既触发 Element Plus 的 prop 校验告警，
 * 又让「不想强调」的待执行标签回落到基础 .el-tag（蓝色）反而最显眼。
 * 与 `Task.vue` 2026-09-14 修的是同一处（提交 761221a1）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PlanDetail from '../PlanDetail.vue'
import { mountOptions, visibleDialogStub } from '@/views/device/__tests__/mount'

vi.mock('@/api/inspection', () => ({
  getInspectionPlanDetail: vi.fn(),
  getInspectionTasks: vi.fn(),
}))

import { getInspectionPlanDetail, getInspectionTasks } from '@/api/inspection'

const PLAN_DETAIL = {
  code: 200,
  data: {
    id: 7,
    plan_name: '每日巡检-总部大楼',
    org_id: 21,
    device_type_id: null,
    cycle_type: 'daily',
    responsible_user_id: 3,
    responsible_user_name: '张三',
    start_date: '2026-09-01',
    end_date: null,
    is_enabled: true,
    created_at: '2026-09-01T08:00:00',
    total_tasks: 14,
    completed_tasks: 12,
    missed_tasks: 1,
    completion_rate: 0.857,
  },
}

const TASK_PAGE = {
  code: 200,
  data: {
    items: [
      {
        id: 44,
        plan_id: 7,
        task_date: '2026-09-14',
        status: 'pending',
        completed_at: null,
        created_at: '2026-09-14T00:05:00',
        plan_name: '每日巡检-总部大楼',
        plan_cycle_type: 'daily',
        records_count: 2,
      },
    ],
    total: 1,
    page: 1,
    page_size: 20,
  },
}

/** 按表头文案找列序号（避免把列顺序写死在断言里） */
function columnIndex(wrapper, label) {
  return wrapper
    .findAll('.el-table__header th .cell')
    .findIndex((th) => th.text().trim() === label)
}

function mountDetail(props = {}) {
  const options = mountOptions(['inspection:view'])
  options.global.stubs = {
    ...options.global.stubs,
    ElDialog: visibleDialogStub(),
  }
  return mount(PlanDetail, {
    props: { planId: 7, modelValue: false, ...props },
    global: options.global,
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  getInspectionPlanDetail.mockResolvedValue(PLAN_DETAIL)
  getInspectionTasks.mockResolvedValue(TASK_PAGE)
})

describe('PlanDetail.vue', () => {
  it('T1: modelValue=true 时弹窗必须真的打开', async () => {
    const wrapper = mountDetail({ modelValue: true })
    await flushPromises()

    expect(wrapper.find('.el-dialog-open').exists()).toBe(true)
  })

  it('T2: 打开时按 planId 拉计划详情', async () => {
    const wrapper = mountDetail({ modelValue: true })
    await flushPromises()

    expect(getInspectionPlanDetail).toHaveBeenCalledWith(7)
    expect(wrapper.text()).toContain('每日巡检-总部大楼')
  })

  it('T3: 任务列表必须按 plan_id 过滤，不能把全量任务当成该计划的任务', async () => {
    const wrapper = mountDetail({ modelValue: true })
    await flushPromises()

    expect(getInspectionTasks).toHaveBeenCalledWith(
      expect.objectContaining({ plan_id: 7 })
    )
  })

  it('T4: 记录数列读 records_count（后端真实计数），不是恒空的 records', async () => {
    const wrapper = mountDetail({ modelValue: true })
    await flushPromises()

    // 后端列表接口不返回 records 列表；模板若读 row.records?.length 必然恒为 0
    expect(wrapper.vm.taskList[0].records).toBeUndefined()

    // 关键：核对**渲染出来的格子**，而不是只核对 mock 数据透传。
    // 只断言 taskList[0].records_count === 2 是在断言 mock 自己，改坏了模板它照样绿。
    const idx = columnIndex(wrapper, '记录数')
    expect(idx, '表头里找不到「记录数」列').toBeGreaterThanOrEqual(0)
    const firstRow = wrapper.findAll('.el-table__body tbody tr')[0]
    expect(firstRow.findAll('td')[idx].text()).toBe('2')
  })

  it('T5: 待执行状态的 el-tag 不得用空串 type', async () => {
    const wrapper = mountDetail({ modelValue: true })
    await flushPromises()

    expect(wrapper.vm.taskStatusType('pending')).not.toBe('')

    // 空串会渲染出 `el-tag--`（不存在的 class）→ 回落到蓝色基础样式
    const bad = wrapper.findAll('.el-tag').filter((t) => t.classes().includes('el-tag--'))
    expect(bad, '存在 type 为空串的 el-tag').toHaveLength(0)
  })

  it('T6: 关闭时 emit update:modelValue(false)', async () => {
    const wrapper = mountDetail({ modelValue: true })
    await flushPromises()

    await wrapper.find('.el-dialog-close').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('T7: modelValue=false 时不渲染内容', async () => {
    const wrapper = mountDetail({ modelValue: false })
    await flushPromises()

    expect(wrapper.find('.el-dialog-open').exists()).toBe(false)
  })
})
