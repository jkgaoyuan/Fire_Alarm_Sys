/**
 * 维修工单列表页（3.7-F1）
 *
 * 覆盖：列表渲染、状态筛选、创建工单、状态流转操作、详情查看
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import OrderList from '../OrderList.vue'
import { findButton, mountOptions, overlayStub } from '@/views/device/__tests__/mount'

vi.mock('@/api/repair', () => ({
  getRepairOrders: vi.fn(),
  createRepairOrder: vi.fn(),
  assignRepairOrder: vi.fn(),
  completeRepairOrder: vi.fn(),
  acceptRepairOrder: vi.fn(),
  returnRepairOrder: vi.fn(),
}))

vi.mock('@/api/device', () => ({
  getDevices: vi.fn().mockResolvedValue({ data: { items: [] } }),
}))

import { getRepairOrders, acceptRepairOrder } from '@/api/repair'

function order(id, overrides = {}) {
  return {
    id,
    order_no: `RO-20260910-${String(id).padStart(3, '0')}`,
    device_id: 1,
    device_name: '1F大厅烟感A01',
    device_code: 'DEV-SMK-001',
    fault_desc: '设备故障',
    status: 'pending',
    reporter_id: 1,
    reporter_name: 'admin',
    repairer_id: null,
    repairer_name: null,
    acceptor_id: null,
    acceptor_name: null,
    assigned_at: null,
    completed_at: null,
    accepted_at: null,
    repair_result: null,
    return_reason: null,
    created_by: 1,
    ...overrides,
  }
}

async function mountOrderList() {
  const options = mountOptions([])
  options.global.stubs = {
    ...options.global.stubs,
    ElDialog: overlayStub(),
    OrderForm: true,
    OrderDetail: true,
  }
  const wrapper = mount(OrderList, options)
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  // 维修接口自 2026-09-13 起因统一信封 {code, message, data}，组件也改回
  // 读 `res.data.items`。mock 必须与后端真实形状一致——这里曾因为 mock 与
  // 组件各写各的形状而整片假绿/假红过。
  getRepairOrders.mockResolvedValue({
    code: 200,
    message: 'success',
    data: {
      items: [
        order(1, { status: 'pending' }),
        order(2, { status: 'repairing', repairer_name: '张三' }),
        order(3, { status: 'completed' }),
      ],
      total: 3,
    },
  })
})

describe('维修工单列表页（3.7-F1）', () => {
  it('T1: 渲染工单表格并展示编号、设备名称、状态', async () => {
    const wrapper = await mountOrderList()

    expect(getRepairOrders).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 20 })
    )
    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(rows).toHaveLength(3)

    // 工单编号
    expect(rows[0].text()).toContain('RO-20260910-001')
    // 设备名称
    expect(rows[0].text()).toContain('1F大厅烟感A01')
    // 状态
    expect(rows[0].text()).toContain('待派单')
    expect(rows[1].text()).toContain('维修中')
    expect(rows[2].text()).toContain('已完成')
  })

  it('T2: 状态筛选把所选值透传给查询接口', async () => {
    const wrapper = await mountOrderList()

    wrapper.vm.filters.status = 'repairing'
    await findButton(wrapper, '查询').trigger('click')
    await flushPromises()

    expect(getRepairOrders).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'repairing', page: 1 })
    )
  })

  it('T3: 待派单工单显示派单按钮', async () => {
    const wrapper = await mountOrderList()

    const rows = wrapper.findAll('.el-table__body tbody tr')
    // 第一行是 pending 状态，应显示派单按钮
    expect(rows[0].text()).toContain('派单')
    // 第二行是 repairing 状态，不应显示派单按钮
    expect(rows[1].text()).not.toContain('派单')
  })

  it('T4: 维修中工单显示完成维修按钮', async () => {
    const wrapper = await mountOrderList()

    const rows = wrapper.findAll('.el-table__body tbody tr')
    // 第二行是 repairing 状态，应显示完成维修按钮
    expect(rows[1].text()).toContain('完成维修')
  })

  it('T5: 待验收工单显示验收通过和验收退回按钮', async () => {
    getRepairOrders.mockResolvedValue({
      code: 200,
      message: 'success',
      data: {
        items: [order(4, { status: 'pending_accept' })],
        total: 1,
      },
    })
    const wrapper = await mountOrderList()

    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(rows[0].text()).toContain('验收通过')
    expect(rows[0].text()).toContain('验收退回')
  })

  it('T6: 点击详情按钮打开详情弹窗', async () => {
    const wrapper = await mountOrderList()

    await findButton(wrapper.findAll('.el-table__body tbody tr')[0], '详情').trigger('click')
    await flushPromises()

    // 详情弹窗应已打开
    expect(wrapper.vm.detailVisible).toBe(true)
    expect(wrapper.vm.currentOrder).toBeTruthy()
    expect(wrapper.vm.currentOrder.id).toBe(1)
  })

  it('T7: 点击创建工单按钮打开创建弹窗', async () => {
    const wrapper = await mountOrderList()

    await findButton(wrapper, '创建工单').trigger('click')
    await flushPromises()

    expect(wrapper.vm.formVisible).toBe(true)
  })

  it('T8: 重置筛选条件后重新查询', async () => {
    const wrapper = await mountOrderList()

    wrapper.vm.filters.status = 'completed'
    await findButton(wrapper, '重置').trigger('click')
    await flushPromises()

    expect(wrapper.vm.filters.status).toBeNull()
    expect(getRepairOrders).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, status: undefined })
    )
  })

  it('T9: 分页切换触发数据加载', async () => {
    const wrapper = await mountOrderList()

    wrapper.vm.pagination.page = 2
    await wrapper.vm.handlePageChange(2)
    await flushPromises()

    expect(getRepairOrders).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2 })
    )
  })

  it('T10: 状态标签映射正确', async () => {
    const wrapper = await mountOrderList()
    
    expect(wrapper.vm.statusLabel('pending')).toBe('待派单')
    expect(wrapper.vm.statusLabel('assigned')).toBe('已派单')
    expect(wrapper.vm.statusLabel('repairing')).toBe('维修中')
    expect(wrapper.vm.statusLabel('pending_accept')).toBe('待验收')
    expect(wrapper.vm.statusLabel('completed')).toBe('已完成')
    expect(wrapper.vm.statusLabel('returned')).toBe('已退回')
  })
})
