/**
 * 巡检计划表单（PlanForm）
 *
 * 覆盖：字段渲染、必填校验、新增/编辑提交、取消关闭
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import PlanForm from '../PlanForm.vue'
import { mountOptions, overlayStub } from '@/views/device/__tests__/mount'

vi.mock('@/api/inspection', () => ({
  createInspectionPlan: vi.fn(),
  updateInspectionPlan: vi.fn(),
}))

vi.mock('@/api/user', () => ({
  getUsers: vi.fn(),
}))

import { createInspectionPlan, updateInspectionPlan } from '@/api/inspection'
import { getUsers } from '@/api/user'

function mountForm(props = {}) {
  const options = mountOptions([])
  options.global.stubs = {
    ...options.global.stubs,
    ElDialog: overlayStub(),
  }
  return mount(PlanForm, {
    props: {
      modelValue: true,
      orgOptions: [{ id: 1, org_name: '总部大楼', children: [] }],
      deviceTypes: [{ id: 11, type_name: '烟感探测器' }],
      ...props,
    },
    global: options.global,
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  getUsers.mockResolvedValue({
    data: {
      items: [{ id: 3, real_name: '张三', username: 'zhangsan' }],
      total: 1,
    },
  })
})

describe('PlanForm.vue', () => {
  it('T1: 渲染表单字段', async () => {
    const wrapper = mountForm()
    await flushPromises()

    const labels = wrapper.findAll('.el-form-item__label').map((l) => l.text())
    expect(labels).toContain('计划名称')
    expect(labels).toContain('所属区域')
    expect(labels).toContain('设备类型')
    expect(labels).toContain('周期类型')
    expect(labels).toContain('责任人')
    expect(labels).toContain('开始日期')
    expect(labels).toContain('结束日期')
    expect(labels).toContain('启用状态')
  })

  it('T2: 必填校验拦截空提交', async () => {
    const wrapper = mountForm()
    await flushPromises()

    const submitBtn = wrapper
      .findAll('button')
      .find((b) => b.text().includes('确定'))
    await submitBtn.trigger('click')
    // async-validator 是异步的，需等两轮微任务让错误态落到 DOM
    await flushPromises()
    await flushPromises()

    // Element Plus 2.x 用 is-error 标记校验失败项
    expect(wrapper.findAll('.el-form-item.is-error').length).toBeGreaterThan(0)
  })

  it('T3: 新增模式提交成功', async () => {
    createInspectionPlan.mockResolvedValue({ code: 200 })
    const wrapper = mountForm()
    await flushPromises()

    wrapper.vm.formData.plan_name = '新增测试计划'
    wrapper.vm.formData.org_id = 1
    wrapper.vm.formData.responsible_user_id = 3
    wrapper.vm.formData.start_date = '2026-09-01'
    await flushPromises()

    const submitBtn = wrapper
      .findAll('button')
      .find((b) => b.text().includes('确定'))
    await submitBtn.trigger('click')
    await flushPromises()

    expect(createInspectionPlan).toHaveBeenCalledWith(
      expect.objectContaining({
        plan_name: '新增测试计划',
        org_id: 1,
        responsible_user_id: 3,
        start_date: '2026-09-01',
      })
    )
    expect(wrapper.emitted('success')).toBeDefined()
  })

  it('T4: 编辑模式提交成功', async () => {
    // 用后端真实的成功信封（message 为中文），而不是空壳 { code: 200 }
    updateInspectionPlan.mockResolvedValue({ code: 200, message: '更新成功' })
    const wrapper = mountForm({
      plan: {
        id: 1,
        plan_name: '原名称',
        org_id: 1,
        device_type_id: 11,
        cycle_type: 'daily',
        responsible_user_id: 3,
        start_date: '2026-09-01',
        end_date: null,
        is_enabled: true,
      },
    })
    await flushPromises()

    wrapper.vm.formData.plan_name = '修改后名称'
    await flushPromises()

    const submitBtn = wrapper
      .findAll('button')
      .find((b) => b.text().includes('确定'))
    await submitBtn.trigger('click')
    await flushPromises()

    expect(updateInspectionPlan).toHaveBeenCalledWith(
      1,
      expect.objectContaining({
        plan_name: '修改后名称',
      })
    )
    expect(wrapper.emitted('success')).toBeDefined()
  })

  it('T6: 编辑提交成功后不得弹出错误提示', async () => {
    // 守护线上症状：后端 PUT 一度返回信封 code=201/message="Created"，
    // 而提交分支判的是 `result.code === 200` → 数据已落库却弹出文案为 "Created" 的
    // 错误提示，且不 emit success。此处钉死「成功信封必须走成功分支」。
    updateInspectionPlan.mockResolvedValue({ code: 200, message: '更新成功' })
    const errorSpy = vi.spyOn(ElMessage, 'error')

    const wrapper = mountForm({
      plan: {
        id: 2,
        plan_name: '原名称',
        org_id: 1,
        device_type_id: 11,
        cycle_type: 'daily',
        responsible_user_id: 3,
        start_date: '2026-09-01',
        end_date: null,
        is_enabled: true,
      },
    })
    await flushPromises()

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('确定'))
    await submitBtn.trigger('click')
    await flushPromises()

    expect(errorSpy).not.toHaveBeenCalled()
    expect(wrapper.emitted('success')).toBeDefined()

    errorSpy.mockRestore()
  })

  it('T5: 取消关闭弹窗并 emit update:modelValue', async () => {
    const wrapper = mountForm()
    await flushPromises()

    const cancelBtn = wrapper
      .findAll('button')
      .find((b) => b.text().includes('取消'))
    await cancelBtn.trigger('click')
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')).toBeDefined()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
  })
})
