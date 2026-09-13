/**
 * 巡检计划列表页（3.6-F1）
 *
 * 覆盖：列表渲染、ID→名称映射、状态标签、操作列按钮、筛选分页、弹窗交互
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessageBox } from 'element-plus'
import Plan from '../Plan.vue'
import { findButton, mountOptions, overlayStub } from '@/views/device/__tests__/mount'

vi.mock('@/api/inspection', () => ({
  getInspectionPlans: vi.fn(),
  createInspectionPlan: vi.fn(),
  updateInspectionPlan: vi.fn(),
  deleteInspectionPlan: vi.fn(),
  toggleInspectionPlanStatus: vi.fn(),
  generateInspectionTasks: vi.fn(),
  getInspectionPlanDetail: vi.fn(),
  getInspectionTasks: vi.fn(),
}))

vi.mock('@/api/organization', () => ({
  getOrganizationTree: vi.fn(),
}))

vi.mock('@/api/device', () => ({
  getDeviceTypes: vi.fn(),
}))

vi.mock('@/api/user', () => ({
  getUsers: vi.fn(),
}))

import {
  getInspectionPlans,
  generateInspectionTasks,
  toggleInspectionPlanStatus,
  deleteInspectionPlan,
} from '@/api/inspection'
import { getOrganizationTree } from '@/api/organization'
import { getDeviceTypes } from '@/api/device'
import { getUsers } from '@/api/user'

function plan(id, overrides = {}) {
  return {
    id,
    plan_name: '每日巡检',
    org_id: 1,
    device_type_id: 11,
    cycle_type: 'daily',
    responsible_user_id: 3,
    start_date: '2026-09-01',
    end_date: '2026-12-31',
    is_enabled: true,
    total_tasks: 10,
    completed_tasks: 5,
    missed_tasks: 0,
    completion_rate: 0.5,
    ...overrides,
  }
}

async function mountPlan() {
  const options = mountOptions([
    'inspection:view',
    'inspection:create',
    'inspection:update',
    'inspection:delete',
  ])
  options.global.stubs = {
    ...options.global.stubs,
    ElDialog: overlayStub(),
    PlanForm: true,
    PlanDetail: true,
  }
  const wrapper = mount(Plan, options)
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()

  getInspectionPlans.mockResolvedValue({
    data: {
      items: [plan(1), plan(2, { cycle_type: 'weekly', is_enabled: false })],
      total: 2,
    },
  })

  getOrganizationTree.mockResolvedValue({
    data: [{ id: 1, org_name: '总部大楼', children: [] }],
  })

  getDeviceTypes.mockResolvedValue({
    data: [{ id: 11, type_name: '烟感探测器' }],
  })

  getUsers.mockResolvedValue({
    data: {
      items: [{ id: 3, real_name: '张三', username: 'zhangsan' }],
      total: 1,
    },
  })
})

describe('巡检计划列表页（3.6-F1）', () => {
  it('T1: 渲染表格并展示计划名称、区域映射、设备类型映射', async () => {
    const wrapper = await mountPlan()

    expect(getInspectionPlans).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 20 })
    )
    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(rows).toHaveLength(2)

    // 第一行：每日巡检计划
    expect(rows[0].text()).toContain('每日巡检')
    expect(rows[0].text()).toContain('总部大楼') // getOrgName 映射
    expect(rows[0].text()).toContain('烟感探测器') // getDeviceTypeName 映射
  })

  it('T2: 周期类型标签映射正确', async () => {
    const wrapper = await mountPlan()

    expect(wrapper.vm.cycleTypeLabel('daily')).toBe('每日')
    expect(wrapper.vm.cycleTypeLabel('weekly')).toBe('每周')
    expect(wrapper.vm.cycleTypeTag('weekly')).toBe('warning')
    expect(wrapper.vm.cycleTypeTag('yearly')).toBe('success')
  })

  it('T3: 责任人映射正确', async () => {
    const wrapper = await mountPlan()

    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(rows[0].text()).toContain('张三')
  })

  it('T4: 状态标签映射正确', async () => {
    const wrapper = await mountPlan()

    const rows = wrapper.findAll('.el-table__body tbody tr')
    // 第一行启用中
    expect(rows[0].text()).toContain('启用中')
    // 第二行已停用
    expect(rows[1].text()).toContain('已停用')
  })

  it('T5: 操作列按钮可见性', async () => {
    const wrapper = await mountPlan()

    const rows = wrapper.findAll('.el-table__body tbody tr')
    const rowText = rows[0].text()
    expect(rowText).toContain('查看详情')
    expect(rowText).toContain('编辑')
    expect(rowText).toContain('生成任务')
    expect(rowText).toContain('停用')
    expect(rowText).toContain('删除')

    // 第二行已停用，按钮应为「启用」
    expect(rows[1].text()).toContain('启用')
  })

  it('T6: 状态筛选把所选值透传给查询接口', async () => {
    const wrapper = await mountPlan()

    wrapper.vm.searchForm.is_enabled = false
    await findButton(wrapper, '搜索').trigger('click')
    await flushPromises()

    expect(getInspectionPlans).toHaveBeenLastCalledWith(
      expect.objectContaining({ is_enabled: false, page: 1 })
    )
  })

  it('T7: 区域筛选透传 org_id', async () => {
    const wrapper = await mountPlan()

    wrapper.vm.searchForm.org_id = 1
    await findButton(wrapper, '搜索').trigger('click')
    await flushPromises()

    expect(getInspectionPlans).toHaveBeenLastCalledWith(
      expect.objectContaining({ org_id: 1, page: 1 })
    )
  })

  it('T8: 分页切换触发数据加载', async () => {
    const wrapper = await mountPlan()

    wrapper.vm.pagination.page = 2
    await wrapper.vm.handlePageChange(2)
    await flushPromises()

    expect(getInspectionPlans).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2 })
    )
  })

  it('T9: 点击新增计划打开 PlanForm 弹窗', async () => {
    const wrapper = await mountPlan()

    await findButton(wrapper, '新增计划').trigger('click')
    await flushPromises()

    expect(wrapper.vm.formVisible).toBe(true)
    expect(wrapper.vm.currentPlan).toBeNull()
  })

  it('T10: 点击编辑打开 PlanForm 并传入当前计划', async () => {
    const wrapper = await mountPlan()

    const rows = wrapper.findAll('.el-table__body tbody tr')
    await findButton(rows[0], '编辑').trigger('click')
    await flushPromises()

    expect(wrapper.vm.formVisible).toBe(true)
    expect(wrapper.vm.currentPlan.id).toBe(1)
  })

  it('T11: 点击生成任务调用接口并刷新列表', async () => {
    generateInspectionTasks.mockResolvedValue({ code: 200 })
    const wrapper = await mountPlan()
    getInspectionPlans.mockClear()

    const rows = wrapper.findAll('.el-table__body tbody tr')
    await findButton(rows[0], '生成任务').trigger('click')
    await flushPromises()

    expect(generateInspectionTasks).toHaveBeenCalledWith(1, { days: 7 })
    // 成功后应重新拉取列表
    expect(getInspectionPlans).toHaveBeenCalled()
  })

  it('T12: 点击停用调用切换接口并传入取反后的状态', async () => {
    toggleInspectionPlanStatus.mockResolvedValue({ code: 201 })
    const wrapper = await mountPlan()

    const rows = wrapper.findAll('.el-table__body tbody tr')
    // 第一行 is_enabled=true，按钮为「停用」，取反应为 false
    await findButton(rows[0], '停用').trigger('click')
    await flushPromises()

    expect(toggleInspectionPlanStatus).toHaveBeenCalledWith(1, { is_enabled: false })
  })

  it('T13: 点击启用调用切换接口并传入 true', async () => {
    toggleInspectionPlanStatus.mockResolvedValue({ code: 201 })
    const wrapper = await mountPlan()

    const rows = wrapper.findAll('.el-table__body tbody tr')
    // 第二行 is_enabled=false，按钮为「启用」
    await findButton(rows[1], '启用').trigger('click')
    await flushPromises()

    expect(toggleInspectionPlanStatus).toHaveBeenCalledWith(2, { is_enabled: true })
  })

  it('T14: 删除需二次确认，确认后调用删除接口', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    deleteInspectionPlan.mockResolvedValue({ code: 200 })
    const wrapper = await mountPlan()

    const rows = wrapper.findAll('.el-table__body tbody tr')
    await findButton(rows[0], '删除').trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalled()
    expect(deleteInspectionPlan).toHaveBeenCalledWith(1)
  })

  it('T15: 取消二次确认时不调用删除接口', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
    const wrapper = await mountPlan()

    const rows = wrapper.findAll('.el-table__body tbody tr')
    await findButton(rows[0], '删除').trigger('click')
    await flushPromises()

    expect(deleteInspectionPlan).not.toHaveBeenCalled()
  })
})
