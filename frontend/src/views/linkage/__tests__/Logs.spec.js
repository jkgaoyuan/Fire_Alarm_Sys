/**
 * 联动日志页（Logs.vue，3.4-B5）
 *
 * 这个页面此前**根本不存在**：后端列表/详情/导出三个端点、`api/linkage.js`
 * 里的 `getLinkageLogs` / `getLogDetail` / `exportLinkageLogs` 全都写好了，
 * 但没有任何视图消费它们——联动日志功能从未对用户可见。
 *
 * 覆盖重点：**演练标记**（本页存在的理由：模拟测试跑出的日志与真实火警产生
 * 的日志，不看这个标记长得一模一样）与**响应信封的读取**。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { findButton, mountOptions } from '@/views/device/__tests__/mount'

vi.mock('@/api/linkage', () => ({
  getLinkageLogs: vi.fn(),
  exportLinkageLogs: vi.fn(),
}))

import Logs from '../Logs.vue'
import { getLinkageLogs } from '@/api/linkage'

function log(id, overrides = {}) {
  return {
    id,
    alarm_id: 100 + id,
    plan_id: 1,
    plan_name: '一层疏散预案',
    action_type: 'start_exhaust',
    target_device_id: 9,
    target_device_name: '排烟风机-01',
    status: 'success',
    result_message: '排烟风机已启动',
    is_simulation: false,
    is_drill: false,
    delay_seconds: 0,
    created_at: '2026-09-16T14:32:10',
    ...overrides,
  }
}

/** 后端真实形状：统一信封 */
function envelope(items, total = items.length) {
  return {
    code: 200,
    message: 'success',
    data: { items, total, page: 1, page_size: 20 },
  }
}

async function mountLogs() {
  const wrapper = mount(Logs, mountOptions())
  await flushPromises()
  return wrapper
}

function rows(wrapper) {
  return wrapper.findAll('.el-table__body tbody tr')
}

/** 列序：ID / 时间 / 预案 / 动作 / 目标设备 / 状态 / 演练·模拟 / 结果说明 */
const DRILL_COLUMN = 6

beforeEach(() => {
  vi.clearAllMocks()
  getLinkageLogs.mockResolvedValue(envelope([log(1), log(2)]))
})

describe('联动日志页（3.4-B5）', () => {
  it('L1: 按统一信封读取并渲染展示字段', async () => {
    const wrapper = await mountLogs()

    expect(rows(wrapper)).toHaveLength(2)
    expect(rows(wrapper)[0].findAll('td')[2].text()).toBe('一层疏散预案')
    expect(rows(wrapper)[0].findAll('td')[4].text()).toBe('排烟风机-01')
    // 动作类型显示中文，而不是原始 start_exhaust
    expect(rows(wrapper)[0].findAll('td')[3].text()).toBe('启动排烟')
  })

  it('L2: 演练告警产生的日志带「演练」标记', async () => {
    getLinkageLogs.mockResolvedValue(
      envelope([log(1, { is_drill: true }), log(2)])
    )
    const wrapper = await mountLogs()

    expect(rows(wrapper)[0].findAll('td')[DRILL_COLUMN].text()).toBe('演练')
    expect(rows(wrapper)[1].findAll('td')[DRILL_COLUMN].text()).toBe('-')
  })

  it('L3: 历史模拟日志（无告警）显示「模拟」而非「演练」', async () => {
    getLinkageLogs.mockResolvedValue(
      envelope([log(1, { is_simulation: true, alarm_id: null })])
    )
    const wrapper = await mountLogs()

    expect(rows(wrapper)[0].findAll('td')[DRILL_COLUMN].text()).toBe('模拟')
  })

  it('L4: 分页总数从 data.total 读取', async () => {
    getLinkageLogs.mockResolvedValue(envelope([log(1)], 128))
    const wrapper = await mountLogs()

    expect(wrapper.findComponent({ name: 'ElPagination' }).props('total')).toBe(128)
  })

  it('L5: 收到裸返回（旧形状）时不得当成成功', async () => {
    getLinkageLogs.mockResolvedValue({
      items: [log(1)],
      total: 1,
      page: 1,
      page_size: 20,
    })

    const wrapper = await mountLogs()

    expect(rows(wrapper)).toHaveLength(0)
  })

  it('L6: 筛选条件透传，空值不上送（后端是 Optional[int]，空串会 422）', async () => {
    const wrapper = await mountLogs()
    getLinkageLogs.mockClear()

    wrapper.vm.filters.status = 'failed'
    await findButton(wrapper, '查询').trigger('click')
    await flushPromises()

    const params = getLinkageLogs.mock.calls[0][0]
    expect(params.status).toBe('failed')
    expect(params.plan_id).toBeUndefined()
    expect(params.alarm_id).toBeUndefined()
    expect(params.page).toBe(1)
  })

  it('L7: 接口失败时不抛错，列表保持为空', async () => {
    getLinkageLogs.mockRejectedValue(new Error('后端不可达'))

    const wrapper = await mountLogs()

    expect(rows(wrapper)).toHaveLength(0)
  })
})
