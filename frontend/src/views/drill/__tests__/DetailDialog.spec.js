/**
 * 演练详情弹窗测试
 * 3.8-F1/F2
 *
 * 本文件此前**不存在**。testing-guidelines 第 31 条：stub 掉一个组件就等于
 * 放弃了对它的所有验证，被 stub 的组件必须另有自己的 spec —— 而本次改的正是
 * 它的「添加参与人员」流程（原生 prompt → 真弹窗），所以必须有。
 *
 * 三处刻意为之，都是为了不写出假绿：
 * 1. el-dialog 用项目既有的 `visibleDialogStub()`（按 modelValue 真渲染），
 *    而不是无条件渲染的 `overlayStub()` —— 后者会把「弹窗没打开」断言成真。
 * 2. el-option 桩真渲染 `label`/`value`，旧写法丢掉它们会让「选项渲染出来了」恒真。
 * 3. 人名断言落在**具体单元格**上（`[data-label="姓名"]` 内的 cell），
 *    不用 `wrapper.text()` 全文子串匹配（第 33 条：易被旁边的文字命中）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import { visibleDialogStub } from '@/views/device/__tests__/mount'

vi.mock('@/api/drill', () => ({
  getDrillDetail: vi.fn().mockResolvedValue({
    data: {
      id: 1,
      drill_name: '秋季疏散演练',
      drill_type: 'evacuation',
      status: 'planned',
      planned_at: '2026-10-01T09:00:00',
      location: 'A 栋',
      participant_count: 2,
      participants: [
        { user_id: 2, role: '指挥员', sign_in_at: null, user_name: '张三' },
        // 该用户已被删除：user_name 为 null，前端须回退显示 #7 而不是空白/裸数字
        { user_id: 7, role: '疏散员', sign_in_at: null, user_name: null },
      ],
      photos: [],
      videos: [],
      evaluation: null,
    },
  }),
  executeDrill: vi.fn().mockResolvedValue({ data: null }),
  completeDrill: vi.fn().mockResolvedValue({ data: null }),
  cancelDrill: vi.fn().mockResolvedValue({ data: null }),
  addDrillParticipant: vi.fn().mockResolvedValue({ data: null }),
  getDrillParticipantCandidates: vi.fn().mockResolvedValue({
    data: [
      { id: 2, username: 'zhangsan', real_name: '张三', role_names: ['指挥员'] },
      { id: 9, username: 'wangwu', real_name: '王五', role_names: ['消防值班员'] },
    ],
  }),
}))

import { getDrillDetail, addDrillParticipant, getDrillParticipantCandidates } from '@/api/drill'
import DetailDialog from '../DetailDialog.vue'

const stubs = {
  // 按 modelValue 真渲染；未打开时内容不在 DOM 里
  'el-dialog': visibleDialogStub(),
  'el-card': {
    template: '<div class="el-card-stub"><slot name="header" /><slot /></div>',
  },
  'el-descriptions': { template: '<div class="el-desc-stub"><slot /></div>' },
  'el-descriptions-item': { template: '<div class="el-desc-item-stub"><slot /></div>' },
  'el-form': { template: '<form class="el-form-stub"><slot /></form>' },
  'el-form-item': { template: '<div class="el-form-item-stub"><slot /></div>' },
  'el-input': { template: '<input class="el-input-stub" />' },
  'el-select': {
    props: ['modelValue', 'loading'],
    emits: ['update:modelValue'],
    template: '<div class="el-select-stub"><slot /></div>',
  },
  'el-option': {
    props: ['label', 'value', 'disabled'],
    template: '<div class="el-option-stub" :data-value="value">{{ label }}</div>',
  },
  'el-button': { template: '<button class="el-button-stub"><slot /></button>' },
  'el-tag': { template: '<span class="el-tag-stub"><slot /></span>' },
  'el-result': { template: '<div class="el-result-stub"><slot name="sub-title" /></div>' },
  'el-empty': { template: '<div class="el-empty-stub"></div>' },
  'el-row': { template: '<div class="el-row-stub"><slot /></div>' },
  'el-col': { template: '<div class="el-col-stub"><slot /></div>' },
  'el-image': { template: '<img class="el-image-stub" />' },
  PermissionButton: { template: '<button class="pb-stub"><slot /></button>' },
  // 让表格桩真渲染每行的单元格，而不是只渲染一个空壳。
  // 注入名不能以 `_` 开头 —— 那是 Vue 保留前缀，会导致注入失效。
  'el-table': {
    props: ['data'],
    provide() {
      return { tableRowsProvider: () => this.data || [] }
    },
    template: '<div class="el-table-stub"><slot /></div>',
  },
  'el-table-column': {
    props: ['prop', 'label'],
    inject: { tableRowsProvider: { default: null } },
    template: `
      <div class="el-col-stub" :data-label="label">
        <div v-for="(row, i) in (tableRowsProvider ? tableRowsProvider() : [])" :key="i" class="el-cell-stub">
          <slot :row="row">{{ prop ? row[prop] : '' }}</slot>
        </div>
      </div>`,
  },
}

function mountDialog(props = {}) {
  return mount(DetailDialog, {
    props: { modelValue: true, drillId: 1, ...props },
    global: { stubs },
  })
}

/** 取某一列下所有单元格的文本 */
function cellsOf(wrapper, label) {
  const col = wrapper.find(`[data-label="${label}"]`)
  if (!col.exists()) return []
  return col.findAll('.el-cell-stub').map(c => c.text())
}

function dialogTitles(wrapper) {
  return wrapper.findAll('.el-dialog-open__title').map(t => t.text())
}

describe('DetailDialog.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('打开时加载详情', async () => {
    mountDialog()
    await flushPromises()
    expect(getDrillDetail).toHaveBeenCalledWith(1)
  })

  // ==================== 人员表显示姓名 ====================

  it('参与人员表显示姓名而非裸用户 ID', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    const names = cellsOf(wrapper, '姓名')
    expect(names).toEqual(['张三', '#7'])
    // 不得再出现「用户 ID」这一列
    expect(wrapper.find('[data-label="用户 ID"]').exists()).toBe(false)
  })

  // ==================== 添加人员改为真弹窗 ====================

  it('点「添加人员」打开真正的弹窗（而不是原生 prompt）', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    // 初始只有详情弹窗本身是打开的
    expect(wrapper.findAll('.el-dialog-open').length).toBe(1)
    expect(dialogTitles(wrapper)).not.toContain('添加参与人员')

    const addBtn = wrapper.findAll('button').find(b => b.text().includes('添加人员'))
    expect(addBtn).toBeTruthy()
    await addBtn.trigger('click')
    await flushPromises()

    // 添加弹窗真的渲染出来了 —— 这正是 overlayStub 会掩盖的那类断言
    expect(dialogTitles(wrapper)).toContain('添加参与人员')
    expect(wrapper.findAll('.el-dialog-open').length).toBe(2)
  })

  it('添加弹窗打开时才拉取候选人，且选项渲染真实姓名', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    expect(getDrillParticipantCandidates).not.toHaveBeenCalled()

    const addBtn = wrapper.findAll('button').find(b => b.text().includes('添加人员'))
    await addBtn.trigger('click')
    await flushPromises()

    expect(getDrillParticipantCandidates).toHaveBeenCalled()
    const texts = wrapper.findAll('.el-option-stub').map(o => o.text())
    expect(texts).toContain('张三')
    expect(texts).toContain('王五')
  })

  // ==================== 提交 ====================

  it('未选择人员就确定时警告且不调用接口', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    const addBtn = wrapper.findAll('button').find(b => b.text().includes('添加人员'))
    await addBtn.trigger('click')
    await flushPromises()

    const confirmBtn = wrapper.findAll('button').find(b => b.text() === '确定')
    await confirmBtn.trigger('click')
    await flushPromises()

    expect(addDrillParticipant).not.toHaveBeenCalled()
  })

  it('确定时按 `{user_id}` 走 body、role 走 query 调用接口', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    const addBtn = wrapper.findAll('button').find(b => b.text().includes('添加人员'))
    await addBtn.trigger('click')
    await flushPromises()

    const vm = wrapper.vm
    vm.addForm.user_id = 9
    vm.addForm.role = '操作员'
    await flushPromises()

    const confirmBtn = wrapper.findAll('button').find(b => b.text() === '确定')
    await confirmBtn.trigger('click')
    await flushPromises()

    // 契约与 api/__tests__/drill.spec.js 里那条一致：data 为 {user_id}，role 为 query
    expect(addDrillParticipant).toHaveBeenCalledWith(1, { user_id: 9 }, '操作员')
  })

  it('角色留空时回落到「参与者」', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    const addBtn = wrapper.findAll('button').find(b => b.text().includes('添加人员'))
    await addBtn.trigger('click')
    await flushPromises()

    wrapper.vm.addForm.user_id = 9
    wrapper.vm.addForm.role = ''

    const confirmBtn = wrapper.findAll('button').find(b => b.text() === '确定')
    await confirmBtn.trigger('click')
    await flushPromises()

    expect(addDrillParticipant).toHaveBeenCalledWith(1, { user_id: 9 }, '参与者')
  })
})
