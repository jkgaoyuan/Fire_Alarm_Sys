/**
 * 演练计划表单弹窗测试
 * 3.8-F2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('@/api/drill', () => ({
  createDrill: vi.fn().mockResolvedValue({ data: { id: 1 } }),
  updateDrill: vi.fn().mockResolvedValue({ data: { id: 1 } }),
  getDrillDetail: vi.fn().mockResolvedValue({
    data: {
      id: 1,
      drill_name: '秋季疏散演练',
      drill_type: 'evacuation',
      planned_at: '2026-10-01T09:00:00',
      location: 'A 栋',
      participants: [{ user_id: 2, role: '指挥员', sign_in_at: null }],
    },
  }),
}))

import { createDrill, updateDrill, getDrillDetail } from '@/api/drill'
import PlanFormDialog from '../PlanFormDialog.vue'

const stubs = {
  // el-dialog 需声明 title prop 才能在文本中断言标题
  'el-dialog': {
    props: ['title', 'modelValue'],
    template: '<div class="el-dialog-stub"><div class="dialog-title">{{ title }}</div><slot /><slot name="footer" /></div>',
  },
  'el-form': {
    template: '<form class="el-form-stub"><slot /></form>',
    methods: {
      validate: () => Promise.resolve(true),
      resetFields: () => {},
    },
  },
  'el-form-item': { template: '<div class="el-form-item-stub"><slot /></div>' },
  'el-input': { template: '<input class="el-input-stub" />' },
  'el-select': { template: '<select class="el-select-stub"><slot /></select>' },
  'el-option': { template: '<option class="el-option-stub"><slot /></option>' },
  'el-date-picker': { template: '<input class="el-date-picker-stub" />' },
  'el-input-number': { template: '<input class="el-input-number-stub" type="number" />' },
  // 不显式 emit click：父级 @click 监听器会 attrs fallthrough 到 button 原生监听，
  // 若 stub 内再 $emit('click') 会导致双次触发
  'el-button': {
    template: '<button class="el-button-stub"><slot /></button>',
  },
}

function mountDialog(props = {}) {
  return mount(PlanFormDialog, {
    props: {
      modelValue: true,
      planData: null,
      ...props,
    },
    global: { stubs },
  })
}

describe('PlanFormDialog.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('新增模式标题为"新增演练计划"', () => {
    const wrapper = mountDialog()
    expect(wrapper.text()).toContain('新增演练计划')
  })

  it('编辑模式标题为"编辑演练计划"', () => {
    const wrapper = mountDialog({ planData: { id: 1 } })
    expect(wrapper.text()).toContain('编辑演练计划')
  })

  it('编辑模式打开时加载演练详情回填表单', async () => {
    mountDialog({ planData: { id: 1 } })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(getDrillDetail).toHaveBeenCalledWith(1)
  })

  it('点击添加参与人员会增加一行', async () => {
    const wrapper = mountDialog()
    const addBtn = wrapper.findAll('button').find(b => b.text().includes('添加参与人员'))
    expect(addBtn).toBeTruthy()
    await addBtn.trigger('click')
    expect(wrapper.findAll('.participant-row').length).toBe(1)
  })

  it('提交新增计划时调用 createDrill 并携带参与人员 ID 列表', async () => {
    const wrapper = mountDialog()
    // 填充表单
    const vm = wrapper.vm
    vm.form.drill_name = '消防演练'
    vm.form.drill_type = 'firefighting'
    vm.form.location = 'B 栋'
    vm.form.participants = [{ user_id: 3, role: '疏散员' }]

    const submitBtn = wrapper.findAll('button').find(b => b.text() === '确定')
    await submitBtn.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(createDrill).toHaveBeenCalledWith({
      drill_name: '消防演练',
      drill_type: 'firefighting',
      planned_at: undefined,
      location: 'B 栋',
      participant_user_ids: [3],
    })
  })

  it('提交编辑计划时调用 updateDrill', async () => {
    const wrapper = mountDialog({ planData: { id: 5 } })
    await new Promise(resolve => setTimeout(resolve, 0))

    const vm = wrapper.vm
    vm.form.drill_name = '更新演练'
    vm.form.drill_type = 'comprehensive'
    vm.form.participants = []

    const submitBtn = wrapper.findAll('button').find(b => b.text() === '确定')
    await submitBtn.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(updateDrill).toHaveBeenCalledWith(5, expect.objectContaining({
      drill_name: '更新演练',
      drill_type: 'comprehensive',
    }))
  })

  it('提交成功后 emit submitted 事件并关闭弹窗', async () => {
    const wrapper = mountDialog()
    const vm = wrapper.vm
    vm.form.drill_name = '演练'
    vm.form.drill_type = 'evacuation'
    vm.form.participants = []

    const submitBtn = wrapper.findAll('button').find(b => b.text() === '确定')
    await submitBtn.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(wrapper.emitted('submitted')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
  })

  it('参与人员 user_id 缺失时警告且不提交', async () => {
    const wrapper = mountDialog()
    const vm = wrapper.vm
    vm.form.drill_name = '演练'
    vm.form.drill_type = 'evacuation'
    vm.form.participants = [{ user_id: undefined, role: 'x' }]

    const submitBtn = wrapper.findAll('button').find(b => b.text() === '确定')
    await submitBtn.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(createDrill).not.toHaveBeenCalled()
  })
})
