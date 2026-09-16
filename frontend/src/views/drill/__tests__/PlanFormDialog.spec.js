/**
 * 演练计划表单弹窗测试
 * 3.8-F2
 *
 * ⚠️ el-select / el-option 的 stub 刻意**真渲染 label 与 value**。
 * 旧版本写成 `<option><slot /></option>`（丢掉 `:label`/`:value`），
 * 用它断言「选项渲染出来了」会**永远为真** —— 与 testing-guidelines 第 31 条
 * 的 `overlayStub` 掩盖「弹窗压根没打开」是同一类假绿。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

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
      participants: [{ user_id: 2, role: '指挥员', sign_in_at: null, user_name: '李四' }],
    },
  }),
  getDrillParticipantCandidates: vi.fn().mockResolvedValue({
    data: [
      { id: 2, username: 'lisi', real_name: '李四', role_names: ['维保人员'] },
      { id: 3, username: 'zhangsan', real_name: '张三', role_names: ['消防值班员'] },
      { id: 4, username: 'nobody', real_name: null, role_names: [] },
    ],
  }),
}))

import { createDrill, updateDrill, getDrillDetail, getDrillParticipantCandidates } from '@/api/drill'
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
  // 真渲染 label / value / disabled —— 见文件头注释
  'el-select': {
    props: ['modelValue', 'loading'],
    emits: ['update:modelValue'],
    template: '<div class="el-select-stub"><slot /></div>',
  },
  'el-option': {
    props: ['label', 'value', 'disabled'],
    template: '<div class="el-option-stub" :data-value="value" :data-disabled="String(!!disabled)">{{ label }}</div>',
  },
  'el-date-picker': { template: '<input class="el-date-picker-stub" />' },
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

function optionTexts(wrapper) {
  return wrapper.findAll('.el-option-stub').map(o => o.text())
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
    await flushPromises()
    expect(getDrillDetail).toHaveBeenCalledWith(1)
  })

  it('点击添加参与人员会增加一行', async () => {
    const wrapper = mountDialog()
    const addBtn = wrapper.findAll('button').find(b => b.text().includes('添加参与人员'))
    expect(addBtn).toBeTruthy()
    await addBtn.trigger('click')
    expect(wrapper.findAll('.participant-row').length).toBe(1)
  })

  // ==================== 人员选择器 ====================

  it('打开弹窗时拉取候选人，且选项渲染出真实姓名', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    expect(getDrillParticipantCandidates).toHaveBeenCalled()

    const addBtn = wrapper.findAll('button').find(b => b.text().includes('添加参与人员'))
    await addBtn.trigger('click')
    await flushPromises()

    const texts = optionTexts(wrapper)
    // 真渲染断言：opt.label 必须落到 DOM 上
    expect(texts).toContain('张三')
    expect(texts).toContain('李四')
    // 缺 real_name 时回退 username，不得渲染成 "undefined"
    expect(texts).toContain('nobody')
    expect(texts.join('|')).not.toContain('undefined')
  })

  it('弹窗未打开时不请求候选人', async () => {
    mountDialog({ modelValue: false })
    await flushPromises()
    expect(getDrillParticipantCandidates).not.toHaveBeenCalled()
  })

  it('已在别行选中的人被置为 disabled，不允许一人占两行', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    const vm = wrapper.vm
    vm.form.participants = [
      { user_id: 3, role: '指挥员' },
      { user_id: undefined, role: '参与者' },
    ]
    await flushPromises()

    // 第二行的选项里，id=3 应被禁用；第一行自己那行则可选
    const rows = wrapper.findAll('.participant-row')
    expect(rows.length).toBe(2)

    const secondRowOptions = rows[1].findAll('.el-option-stub')
    const taken = secondRowOptions.find(o => o.attributes('data-value') === '3')
    expect(taken).toBeTruthy()
    expect(taken.attributes('data-disabled')).toBe('true')

    const firstRowOptions = rows[0].findAll('.el-option-stub')
    const self = firstRowOptions.find(o => o.attributes('data-value') === '3')
    expect(self.attributes('data-disabled')).toBe('false')
  })

  it('新增一行时角色默认为「参与者」', async () => {
    const wrapper = mountDialog()
    const addBtn = wrapper.findAll('button').find(b => b.text().includes('添加参与人员'))
    await addBtn.trigger('click')
    expect(wrapper.vm.form.participants[0].role).toBe('参与者')
  })

  it('编辑回填时保留 user_name，供已停用人员回退显示', async () => {
    const wrapper = mountDialog({ planData: { id: 1 } })
    await flushPromises()
    expect(wrapper.vm.form.participants[0].user_name).toBe('李四')
  })

  // ==================== 提交 ====================

  it('提交新增计划时逐人携带角色（此前角色被无声丢弃）', async () => {
    const wrapper = mountDialog()
    // 填充表单
    const vm = wrapper.vm
    vm.form.drill_name = '消防演练'
    vm.form.drill_type = 'firefighting'
    vm.form.location = 'B 栋'
    vm.form.participants = [{ user_id: 3, role: '疏散员' }]

    const submitBtn = wrapper.findAll('button').find(b => b.text() === '确定')
    await submitBtn.trigger('click')
    await flushPromises()

    expect(createDrill).toHaveBeenCalledWith({
      drill_name: '消防演练',
      drill_type: 'firefighting',
      planned_at: undefined,
      location: 'B 栋',
      participants: [{ user_id: 3, role: '疏散员' }],
    })
  })

  it('角色留空时提交回落到「参与者」', async () => {
    const wrapper = mountDialog()
    const vm = wrapper.vm
    vm.form.drill_name = '演练'
    vm.form.drill_type = 'evacuation'
    vm.form.participants = [{ user_id: 3, role: '' }]

    const submitBtn = wrapper.findAll('button').find(b => b.text() === '确定')
    await submitBtn.trigger('click')
    await flushPromises()

    expect(createDrill).toHaveBeenCalledWith(
      expect.objectContaining({ participants: [{ user_id: 3, role: '参与者' }] })
    )
  })

  it('提交编辑计划时调用 updateDrill', async () => {
    const wrapper = mountDialog({ planData: { id: 5 } })
    await flushPromises()

    const vm = wrapper.vm
    vm.form.drill_name = '更新演练'
    vm.form.drill_type = 'comprehensive'
    vm.form.participants = []

    const submitBtn = wrapper.findAll('button').find(b => b.text() === '确定')
    await submitBtn.trigger('click')
    await flushPromises()

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
    await flushPromises()

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
    await flushPromises()

    expect(createDrill).not.toHaveBeenCalled()
  })
})
