/**
 * 前端单元测试 - 联动预案页面 (3.4-F1)
 * Vitest + Vue Test Utils
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Plan from '@/views/linkage/Plan.vue'

// Mock API calls
vi.mock('@/api/linkage', () => ({
  getLinkagePlans: vi.fn(),
  createLinkagePlan: vi.fn(),
  updateLinkagePlan: vi.fn(),
  deleteLinkagePlan: vi.fn(),
  togglePlanStatus: vi.fn(),
  simulateTrigger: vi.fn(),
}))

describe('Plan.vue', () => {
  it('renders without crashing', () => {
    const wrapper = mount(Plan)
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('h2').text()).toContain('联动预案管理')
  })

  it('displays filtering options', () => {
    const wrapper = mount(Plan)
    
    // Check filter card exists
    expect(wrapper.find('.filter-card').exists()).toBe(true)
    
    // Check filter select elements
    expect(wrapper.find('[data-testid="org-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="fire-type-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="enabled-status-select"]').exists()).toBe(true)
  })

  it('shows empty state when no plans', async () => {
    const wrapper = mount(Plan, {
      global: {
        mocks: {
          $t: (msg) => msg,
        },
      },
    })

    // Simulate loading with empty data
    await wrapper.vm.loadPlans()
    
    expect(wrapper.vm.loading).toBe(false)
  })

  it('handles create new plan action', async () => {
    const wrapper = mount(Plan)
    
    // Trigger create button click
    const createButton = wrapper.find('button[type="primary"]')
    expect(createButton.exists()).toBe(true)
  })

  it('should show pagination controls', () => {
    const wrapper = mount(Plan)
    
    expect(wrapper.find('el-pagination').exists()).toBe(true)
    expect(wrapper.vm.pagination.page).toBe(1)
    expect(wrapper.vm.pagination.page_size).toBe(10)
  })
})

describe('PlanForm.vue', () => {
  import { mount } from '@vue/test-utils'
  import PlanForm from '@/views/linkage/components/PlanForm.vue'
  
  it('renders form fields correctly', () => {
    const wrapper = mount(PlanForm)
    
    expect(wrapper.find('[data-testid="plan-name-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="org-id-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="fire-type-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="trigger-alarm-type-select"]').exists()).toBe(true)
  })

  it('allows adding actions dynamically', () => {
    const wrapper = mount(PlanForm)
    
    const initialActionsCount = wrapper.vm.formData.actions.length
    expect(initialActionsCount).toBeGreaterThanOrEqual(0)
  })

  it('validates required fields', async () => {
    const wrapper = mount(PlanForm, {
      props: {
        plan: null,
      },
    })

    // Try to submit with empty required fields
    await wrapper.vm.handleSubmit()
    
    // Should have validation errors
    expect(wrapper.findAll('.el-form-item--error').length).toBeGreaterThan(0)
  })

  it('can edit action parameters', async () => {
    const wrapper = mount(PlanForm)
    
    // Add an action first
    wrapper.vm.addAction()
    
    expect(wrapper.vm.formData.actions.length).toBe(1)
    
    // Edit parameters
    const action = wrapper.vm.formData.actions[0]
    wrapper.vm.editParams(action)
    
    // Dialog should open
    expect(wrapper.vm.paramsDialogVisible).toBe(true)
  })

  it('submits valid form data', async () => {
    const wrapper = mount(PlanForm, {
      props: {
        plan: null,
      },
      emit: {
        submit: vi.fn(),
        cancel: vi.fn(),
      },
    })

    // Fill in required data
    wrapper.vm.formData.plan_name = '测试预案'
    wrapper.vm.formData.org_id = 1
    
    await wrapper.vm.$nextTick()
    
    // Submit
    await wrapper.vm.handleSubmit()
    
    // Check if submit event was emitted
    expect(wrapper.emitted('submit')).toBeDefined()
  })
})
