/**
 * 联动预案列表页（Plan.vue，3.4-F1）
 *
 * **本文件是重写的**。原文件从落地起就没跑过一条用例：
 * `describe('PlanForm.vue', () => { import ... })` —— 把 `import` 写进了
 * describe 回调体里，`import` 只能在模块顶层，整个文件解析失败
 * （vitest 报 "Cannot parse ..."、0 test）。而且它的断言用的是
 * `[data-testid="plan-name-input"]` 这类标记，`linkage/Plan.vue` 与
 * `linkage/components/PlanForm.vue` 里 **data-testid 出现 0 次**，
 * 即修好语法也照样全红——断言写的是另一个时代的 DOM。
 *
 * 重写触发点：2026-09-13 迁移 `/linkage-plans` 到统一响应信封时改了本组件的
 * 读取方式，而它是唯一能验证该改动的地方，不能继续挂着。
 *
 * 覆盖重点：**响应形状的读取**（这是本次改的东西），而不是罗列元素。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { findButton, mountOptions, overlayStub } from '@/views/device/__tests__/mount'

vi.mock('@/api/linkage', () => ({
  getLinkagePlans: vi.fn(),
  getLinkagePlanDetail: vi.fn(),
  createLinkagePlan: vi.fn(),
  updateLinkagePlan: vi.fn(),
  deleteLinkagePlan: vi.fn(),
  togglePlanStatus: vi.fn(),
  simulateTrigger: vi.fn(),
}))

import Plan from '../Plan.vue'
import { getLinkagePlans } from '@/api/linkage'

function plan(id, overrides = {}) {
  return {
    id,
    plan_name: `预案${id}`,
    org_id: 1,
    fire_type: 'fire',
    trigger_alarm_type: null,
    actions: [{ action_type: 'start_exhaust', params: {} }],
    is_enabled: true,
    organization: { id: 1, org_name: '消防管理中心' },
    ...overrides,
  }
}

/** 后端迁移后的真实形状：统一信封 */
function envelope(items, total = items.length) {
  return {
    code: 200,
    message: 'success',
    data: { items, total, page: 1, page_size: 10 },
  }
}

async function mountPlan() {
  const options = mountOptions([])
  options.global.stubs = {
    ...options.global.stubs,
    ElDialog: overlayStub(),
    ElDrawer: overlayStub(),
  }
  const wrapper = mount(Plan, options)
  await flushPromises()
  return wrapper
}

function rows(wrapper) {
  return wrapper.findAll('.el-table__body tbody tr')
}

beforeEach(() => {
  vi.clearAllMocks()
  getLinkagePlans.mockResolvedValue(envelope([plan(1), plan(2)]))
})

describe('联动预案列表页（3.4-F1）', () => {
  it('T1: 按统一信封读取列表并渲染', async () => {
    const wrapper = await mountPlan()

    expect(rows(wrapper)).toHaveLength(2)
    expect(wrapper.text()).toContain('预案1')
    expect(wrapper.text()).toContain('预案2')
  })

  it('T2: 分页总数从 data.total 读取', async () => {
    getLinkagePlans.mockResolvedValue(envelope([plan(1)], 42))
    const wrapper = await mountPlan()

    const pagination = wrapper.findComponent({ name: 'ElPagination' })
    expect(pagination.props('total')).toBe(42)
  })

  it('T3: 收到裸返回（旧形状）时不得当成成功', async () => {
    // 回归护栏：迁移前这里读的是裸 res.items，为了迁就当时直接返回裸对象的
    // 后端（CLAUDE.md「教训 1」把这个当成了修复）。若哪天后端退回裸返回，
    // 本断言会失败，而不是让页面静默显示空表。
    getLinkagePlans.mockResolvedValue({
      items: [plan(1), plan(2)],
      total: 2,
      page: 1,
      page_size: 10,
    })

    const wrapper = await mountPlan()

    expect(rows(wrapper)).toHaveLength(0)
  })

  it('T4: 筛选条件透传给查询接口', async () => {
    const wrapper = await mountPlan()
    getLinkagePlans.mockClear()

    wrapper.vm.filters.fire_type = 'pre_fire'
    await findButton(wrapper, '查询').trigger('click')
    await flushPromises()

    expect(getLinkagePlans).toHaveBeenCalledWith(
      expect.objectContaining({ fire_type: 'pre_fire', page: 1 })
    )
  })

  it('T5: 接口失败时不抛错，列表保持为空', async () => {
    getLinkagePlans.mockRejectedValue(new Error('后端不可达'))

    const wrapper = await mountPlan()

    expect(rows(wrapper)).toHaveLength(0)
  })
})
