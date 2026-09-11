/**
 * 演练评估打分弹窗测试
 * 3.8-F4
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

vi.mock('@/api/drill', () => ({
  submitDrillEvaluation: vi.fn().mockResolvedValue({ data: { total_score: 28 } }),
  getDrillDetail: vi.fn().mockResolvedValue({
    data: { id: 1, drill_name: '季度综合演练', status: 'completed' },
  }),
}))

import { submitDrillEvaluation, getDrillDetail } from '@/api/drill'
import EvaluationDialog from '../EvaluationDialog.vue'

const stubs = {
  // PermissionButton 依赖全局 v-permission 指令，stub 为普通按钮（点击靠 attrs fallthrough）
  PermissionButton: {
    props: ['permission', 'loading'],
    template: '<button class="pb-stub"><slot /></button>',
  },
  'el-dialog': {
    props: ['title', 'modelValue'],
    template: '<div class="el-dialog-stub"><div class="dialog-title">{{ title }}</div><slot /><slot name="footer" /></div>',
  },
  'el-form': { template: '<form class="el-form-stub"><slot /></form>' },
  'el-form-item': { template: '<div class="el-form-item-stub"><slot /></div>' },
  'el-input': { template: '<input class="el-input-stub" />' },
  'el-row': { template: '<div class="el-row-stub"><slot /></div>' },
  'el-col': { template: '<div class="el-col-stub"><slot /></div>' },
  'el-input-number': { template: '<input class="el-input-number-stub" type="number" />' },
  // 不显式 emit click：父级 @click 监听器会 attrs fallthrough 到 button 原生监听，
  // 若 stub 内再 $emit('click') 会导致双次触发
  'el-button': {
    template: '<button class="el-button-stub"><slot /></button>',
  },
}

function mountDialog(props = {}) {
  return mount(EvaluationDialog, {
    props: {
      modelValue: true,
      drillId: 1,
      ...props,
    },
    global: { stubs },
  })
}

describe('EvaluationDialog.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('弹窗打开时初始化默认 4 个评估项', async () => {
    const wrapper = mountDialog()
    await nextTick()
    expect(wrapper.vm.form.items.length).toBe(4)
  })

  it('弹窗打开时加载演练名称', async () => {
    mountDialog()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(getDrillDetail).toHaveBeenCalledWith(1)
  })

  it('点击添加评估项会增加一项', async () => {
    const wrapper = mountDialog()
    await nextTick()
    const addBtn = wrapper.findAll('button').find(b => b.text().includes('添加评估项'))
    await addBtn.trigger('click')
    expect(wrapper.vm.form.items.length).toBe(5)
  })

  it('总分自动计算所有评估项得分之和', async () => {
    const wrapper = mountDialog()
    await nextTick()
    const vm = wrapper.vm
    vm.form.items = [
      { label: '响应时间', score: 8, max_score: 10, comment: '' },
      { label: '疏散效率', score: 9, max_score: 10, comment: '' },
      { label: '设备联动', score: 6, max_score: 10, comment: '' },
      { label: '人员配合', score: 5, max_score: 10, comment: '' },
    ]
    expect(vm.totalScore).toBe(28)
    expect(vm.maxTotalScore).toBe(40)
  })

  it('删除评估项后总分同步更新', async () => {
    const wrapper = mountDialog()
    await nextTick()
    const vm = wrapper.vm
    vm.form.items = [
      { label: 'A', score: 5, max_score: 10, comment: '' },
      { label: 'B', score: 7, max_score: 10, comment: '' },
    ]
    vm.removeItem(0)
    expect(vm.form.items.length).toBe(1)
    expect(vm.totalScore).toBe(7)
  })

  it('提交评估时携带正确的 payload 结构', async () => {
    const wrapper = mountDialog()
    await nextTick()
    const vm = wrapper.vm
    vm.form.items = [
      { label: '响应时间', score: 8, max_score: 10, comment: '快速' },
    ]
    vm.form.problems = '部分人员迟到'
    vm.form.improvements = '加强培训'
    vm.form.evaluation_summary = '整体良好'

    const submitBtn = wrapper.findAll('button').find(b => b.text().includes('提交评估'))
    await submitBtn.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(submitDrillEvaluation).toHaveBeenCalledWith({
      drill_id: 1,
      items: [{
        item: '响应时间',
        label: '响应时间',
        score: 8,
        max_score: 10,
        comment: '快速',
      }],
      problems: '部分人员迟到',
      improvements: '加强培训',
      evaluation_summary: '整体良好',
    })
  })

  it('评估项标签为空时提交被阻止', async () => {
    const wrapper = mountDialog()
    await nextTick()
    const vm = wrapper.vm
    // 默认项 label 为空
    const submitBtn = wrapper.findAll('button').find(b => b.text().includes('提交评估'))
    await submitBtn.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(submitDrillEvaluation).not.toHaveBeenCalled()
  })

  it('提交成功后 emit submitted 并关闭', async () => {
    const wrapper = mountDialog()
    await nextTick()
    const vm = wrapper.vm
    vm.form.items = [{ label: 'A', score: 5, max_score: 10, comment: '' }]

    const submitBtn = wrapper.findAll('button').find(b => b.text().includes('提交评估'))
    await submitBtn.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(wrapper.emitted('submitted')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
  })

  it('drillName 从详情接口派生', async () => {
    const wrapper = mountDialog()
    await new Promise(resolve => setTimeout(resolve, 10))
    expect(wrapper.vm.drillName).toBe('季度综合演练')
  })
})
