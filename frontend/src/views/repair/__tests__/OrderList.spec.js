/**
 * 维修工单列表页（3.7-F1）
 *
 * 覆盖：列表渲染、状态筛选、创建工单、状态流转操作、详情查看
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import OrderList from '../OrderList.vue'
import {
  findButton,
  mountOptions,
  overlayStub,
  visibleButtonTexts,
} from '@/views/device/__tests__/mount'

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

vi.mock('@/api/repair', () => ({
  getRepairOrders: vi.fn(),
  createRepairOrder: vi.fn(),
  assignRepairOrder: vi.fn(),
  startRepairOrder: vi.fn(),
  completeRepairOrder: vi.fn(),
  acceptRepairOrder: vi.fn(),
  returnRepairOrder: vi.fn(),
}))

vi.mock('@/api/device', () => ({
  getDevices: vi.fn().mockResolvedValue({ data: { items: [] } }),
}))

vi.mock('@/api/user', () => ({
  getUsers: vi.fn().mockResolvedValue({ data: { items: [] } }),
  getMe: vi.fn(),
}))

import { ElMessageBox } from 'element-plus'
import {
  getRepairOrders,
  acceptRepairOrder,
  startRepairOrder,
  completeRepairOrder,
} from '@/api/repair'
import { getUsers } from '@/api/user'
import { useAuthStore } from '@/stores/auth'

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

/**
 * @param {string[]} permissions 当前用户权限码（驱动 v-permission）
 * @param {string[]} roles 当前用户角色码（操作列不应再依赖它，仅用于回归钉死）
 */
async function mountOrderList(permissions = [], roles = []) {
  const options = mountOptions(permissions)
  // mountOptions 内部已 setActivePinia，此处取到的即挂载所用的 store
  useAuthStore().userInfo = { roles }
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

/** 只有 assigned / returned 状态的工单，用于验证状态流转按钮 */
function flowOrders() {
  return {
    code: 200,
    message: 'success',
    data: {
      items: [
        order(5, { status: 'assigned', repairer_name: '张三' }),
        order(6, { status: 'returned', repairer_name: '张三' }),
      ],
      total: 2,
    },
  }
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
    const wrapper = await mountOrderList(['repair:assign'])

    const rows = wrapper.findAll('.el-table__body tbody tr')
    // 第一行是 pending 状态，应显示派单按钮
    expect(visibleButtonTexts(rows[0])).toContain('派单')
    // 第二行是 repairing 状态，不应显示派单按钮
    expect(visibleButtonTexts(rows[1])).not.toContain('派单')
  })

  it('T4: 维修中工单显示完成维修按钮', async () => {
    // 断言**可见性**而非文本：完成维修按钮带 v-permission（隐藏是 display:none，
    // textContent 照样取得到），用 text() 会在按钮被权限隐藏时假绿。
    const wrapper = await mountOrderList(['repair:repair'])

    const rows = wrapper.findAll('.el-table__body tbody tr')
    // 第二行是 repairing 状态，应显示完成维修按钮
    expect(visibleButtonTexts(rows[1])).toContain('完成维修')
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
    const wrapper = await mountOrderList(['repair:accept'])

    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(visibleButtonTexts(rows[0])).toContain('验收通过')
    expect(visibleButtonTexts(rows[0])).toContain('验收退回')
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

describe('开始维修（3.7 FR-039 状态流转）', () => {
  beforeEach(() => {
    getRepairOrders.mockResolvedValue(flowOrders())
    ElMessageBox.confirm.mockResolvedValue('confirm')
    startRepairOrder.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { id: 5, status: 'repairing' },
    })
  })

  it('T11: 持有 repair:repair 时，已派单工单显示「开始维修」', async () => {
    const wrapper = await mountOrderList(['repair:repair'])

    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(visibleButtonTexts(rows[0])).toContain('开始维修')
  })

  it('T12: 无 repair:repair 时不显示「开始维修」', async () => {
    // 不门控会怎样：值班员看得到按钮、点下去后端 403，是个点不动的假按钮。
    // v-permission 是隐藏（display:none）而非移除 DOM，故用 visibleButtonTexts 断言。
    const wrapper = await mountOrderList([])

    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(visibleButtonTexts(rows[0])).not.toContain('开始维修')
  })

  it('T13: 点「开始维修」调 /start 并刷新列表', async () => {
    const wrapper = await mountOrderList(['repair:repair'])

    await findButton(wrapper, '开始维修').trigger('click')
    await flushPromises()

    expect(startRepairOrder).toHaveBeenCalledWith(5)
    // 初次加载 + 操作后刷新
    expect(getRepairOrders).toHaveBeenCalledTimes(2)
  })

  it('T14: 已退回工单的「重新维修」调 /start，而不是 /complete', async () => {
    // 接到 /complete 上是既有缺陷：complete 要求 status === 'repairing'，
    // 对付 returned 工单必然 400，退回的单从此无路可走。
    const wrapper = await mountOrderList(['repair:repair'])

    await findButton(wrapper, '重新维修').trigger('click')
    await flushPromises()

    expect(startRepairOrder).toHaveBeenCalledWith(6)
    expect(completeRepairOrder).not.toHaveBeenCalled()
  })

  it('T15: 维修人候选查询只向持有 repair:repair 的用户要数据', async () => {
    const wrapper = await mountOrderList(['repair:repair'])

    await wrapper.vm.loadRepairerOptions()
    await flushPromises()

    expect(getUsers).toHaveBeenCalledWith(
      expect.objectContaining({ permission: 'repair:repair' })
    )
  })
})

describe('操作列权限门控（与后端同口径：判权限码，不判角色码）', () => {
  function onlyPending() {
    return {
      code: 200,
      message: 'success',
      data: { items: [order(7, { status: 'pending' })], total: 1 },
    }
  }

  function onlyPendingAccept() {
    return {
      code: 200,
      message: 'success',
      data: { items: [order(8, { status: 'pending_accept' })], total: 1 },
    }
  }

  it('T16: 持有 repair:assign 时显示「派单」', async () => {
    getRepairOrders.mockResolvedValue(onlyPending())
    const wrapper = await mountOrderList(['repair:assign'])

    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(visibleButtonTexts(rows[0])).toContain('派单')
  })

  it('T17: 角色码是 chief 但没有 repair:assign 时不显示「派单」', async () => {
    // 这是本次改造的**核心**：前端原先判 `role_code === 'chief'`，后端判
    // `repair:assign`，两套口径。主管被撤销 repair:assign 后前端仍显示按钮、
    // 点击才 403；反过来给非 chief 角色授予 repair:assign，前端又把按钮藏了。
    // 前端一律改判权限码后，角色码不再影响这个按钮——本用例钉住这一点。
    getRepairOrders.mockResolvedValue(onlyPending())
    const wrapper = await mountOrderList([], ['chief'])

    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(visibleButtonTexts(rows[0])).not.toContain('派单')
  })

  it('T18: 非 chief 角色只要持有 repair:assign 就显示「派单」', async () => {
    getRepairOrders.mockResolvedValue(onlyPending())
    const wrapper = await mountOrderList(['repair:assign'], ['maintainer'])

    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(visibleButtonTexts(rows[0])).toContain('派单')
  })

  it('T19: 持有 repair:accept 时显示验收按钮', async () => {
    getRepairOrders.mockResolvedValue(onlyPendingAccept())
    const wrapper = await mountOrderList(['repair:accept'])

    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(visibleButtonTexts(rows[0])).toContain('验收通过')
    expect(visibleButtonTexts(rows[0])).toContain('验收退回')
  })

  it('T20: 无 repair:accept 时不显示验收按钮', async () => {
    getRepairOrders.mockResolvedValue(onlyPendingAccept())
    const wrapper = await mountOrderList([], ['chief'])

    const rows = wrapper.findAll('.el-table__body tbody tr')
    expect(visibleButtonTexts(rows[0])).not.toContain('验收通过')
    expect(visibleButtonTexts(rows[0])).not.toContain('验收退回')
  })
})
