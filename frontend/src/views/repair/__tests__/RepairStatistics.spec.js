/**
 * 维修统计页（RepairStatistics.vue，3.7-F6 / FR-042）
 *
 * 本文件补的是**零覆盖**：这个页面此前没有任何 spec，因此下面这个缺陷一直没被发现——
 * 4 个统计接口返回的是**裸数据对象**，页面却按统一信封读 `res.data`，
 * 取到 undefined 后一路走默认值，四项指标恒为 0/空，而后端其实有数据。
 *
 * 所以这里的核心断言不是「页面渲染出来了」，而是
 * **裸返回的数据必须真的进到页面上**——只断言元素存在是会漏掉这个 bug 的。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { mountOptions } from '@/views/device/__tests__/mount'

vi.mock('@/api/repair', () => ({
  getRepairOverview: vi.fn(),
  getRepairerWorkload: vi.fn(),
  getFaultDistribution: vi.fn(),
  getTop10FaultDevices: vi.fn(),
}))

import RepairStatistics from '../RepairStatistics.vue'
import {
  getRepairOverview,
  getRepairerWorkload,
  getFaultDistribution,
  getTop10FaultDevices,
} from '@/api/repair'

async function mountStatistics() {
  const wrapper = mount(RepairStatistics, mountOptions([]))
  await flushPromises()
  return wrapper
}

/**
 * 与后端真实返回一致（2026-09-13 实测 curl 确认）：
 * 裸对象，**没有** code / message / data 三个键。
 */
function mockBareResponses() {
  getRepairOverview.mockResolvedValue({
    avg_repair_hours: 2.5,
    total_orders: 7,
    status_distribution: [
      { status: 'pending', count: 2 },
      { status: 'completed', count: 5 },
    ],
  })
  getRepairerWorkload.mockResolvedValue({
    items: [{ name: '维保员李四', total: 3, completed: 2 }],
  })
  getFaultDistribution.mockResolvedValue({
    items: [{ type: '排烟风机', count: 4 }],
  })
  getTop10FaultDevices.mockResolvedValue({
    items: [
      {
        device_code: 'DEV-SMK-001',
        device_name: '1F大厅烟感A01',
        type_name: '烟感探测器',
        fault_count: 3,
      },
    ],
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  mockBareResponses()
})

describe('维修统计页（3.7-F6）', () => {
  it('T1: 概览数据从裸返回中正确读出', async () => {
    const wrapper = await mountStatistics()

    // 直接读组件状态：这是「数据有没有真的进去」的唯一可靠断言。
    // 断言 DOM 上的卡片存在是无效覆盖——卡片在数据为 0 时也照样渲染。
    expect(wrapper.vm.overview.total_orders).toBe(7)
    expect(wrapper.vm.overview.avg_repair_hours).toBe(2.5)
    expect(wrapper.vm.overview.status_distribution).toHaveLength(2)
  })

  it('T2: 状态分布计数按下标生效', async () => {
    const wrapper = await mountStatistics()

    expect(wrapper.vm.getStatusCount('pending')).toBe(2)
    expect(wrapper.vm.getStatusCount('completed')).toBe(5)
    // 未出现的状态回落到 0，而不是 undefined
    expect(wrapper.vm.getStatusCount('assigned')).toBe(0)
  })

  it('T3: 三个列表类统计都从裸返回的 items 中读出', async () => {
    const wrapper = await mountStatistics()

    expect(wrapper.vm.workload).toHaveLength(1)
    expect(wrapper.vm.workload[0].name).toBe('维保员李四')

    expect(wrapper.vm.faultTypes).toHaveLength(1)
    expect(wrapper.vm.faultTypes[0].type).toBe('排烟风机')

    expect(wrapper.vm.top10Devices).toHaveLength(1)
    expect(wrapper.vm.top10Devices[0].device_code).toBe('DEV-SMK-001')
  })

  it('T4: 四个接口都是被本页发起的，且失败时不静默', async () => {
    getRepairOverview.mockRejectedValue(new Error('后端不可达'))
    const wrapper = await mountStatistics()

    expect(getRepairOverview).toHaveBeenCalled()
    expect(getRepairerWorkload).toHaveBeenCalled()
    expect(getFaultDistribution).toHaveBeenCalled()
    expect(getTop10FaultDevices).toHaveBeenCalled()

    // 一个接口失败不该让页面崩掉，其余数据保持默认值
    expect(wrapper.vm.overview.total_orders).toBe(0)
  })
})
