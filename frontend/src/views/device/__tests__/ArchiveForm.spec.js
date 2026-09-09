import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/api/device', () => ({
  createDevice: vi.fn(),
  updateDevice: vi.fn(),
  getDevices: vi.fn(),
}))

import { createDevice, getDevices, updateDevice } from '@/api/device'
import ArchiveForm from '../ArchiveForm.vue'
import { findButton, overlayOptions, SAMPLE_DEVICE, SAMPLE_TYPES } from './mount'

async function mountForm(props = {}) {
  const wrapper = mount(ArchiveForm, overlayOptions(props))
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  return wrapper
}

function codeInput(wrapper) {
  return wrapper.find('input[placeholder="如 DEV-SMK-001"]')
}

function nameInput(wrapper) {
  return wrapper.find('input[placeholder="请输入设备名称"]')
}

async function fillRequired(wrapper, code = 'DEV-NEW-001') {
  await codeInput(wrapper).setValue(code)
  await nameInput(wrapper).setValue('新设备')
  await findButton(wrapper, '确定').trigger('click')
  await flushPromises()
}

describe('ArchiveForm.vue 设备档案表单', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getDevices.mockResolvedValue({ data: { items: [] } })
  })

  it('必填项为空时拦截提交', async () => {
    const wrapper = await mountForm({ deviceTypes: SAMPLE_TYPES })
    expect(wrapper.text()).toContain('新增设备档案')

    await findButton(wrapper, '确定').trigger('click')
    await flushPromises()

    expect(createDevice).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(wrapper.text()).toContain('请输入设备编码'))
    await vi.waitFor(() => expect(wrapper.text()).toContain('请输入设备名称'))
  })

  it('新增提交时剔除空文本字段并把空日期归一为 null', async () => {
    createDevice.mockResolvedValue({ data: { ...SAMPLE_DEVICE, id: 9 } })
    const wrapper = await mountForm({ deviceTypes: SAMPLE_TYPES })

    await fillRequired(wrapper)

    expect(createDevice).toHaveBeenCalledTimes(1)
    const payload = createDevice.mock.calls[0][0]
    expect(payload).toMatchObject({
      device_code: 'DEV-NEW-001',
      device_name: '新设备',
      status: 'normal',
      install_date: null,
      warranty_expire_date: null,
    })
    expect(payload).not.toHaveProperty('manufacturer')
    expect(payload).not.toHaveProperty('remark')
    expect(wrapper.emitted('success')).toHaveLength(1)
    expect(wrapper.emitted('update:modelValue')).toContainEqual([false])
  })

  it('设备编码重复时阻止提交并给出冲突提示', async () => {
    getDevices.mockResolvedValue({
      data: { items: [{ id: 7, device_code: 'DEV-SMK-001' }] },
    })
    const wrapper = await mountForm({ deviceTypes: SAMPLE_TYPES })

    await fillRequired(wrapper, 'DEV-SMK-001')

    expect(createDevice).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(wrapper.text()).toContain('设备编码已存在: DEV-SMK-001'))
    expect(getDevices).toHaveBeenCalledWith({
      keyword: 'DEV-SMK-001',
      page_size: 100,
      include_retired: true,
    })
  })

  it('编辑模式回填原值并按类型 schema 渲染扩展属性', async () => {
    updateDevice.mockResolvedValue({ data: SAMPLE_DEVICE })
    const wrapper = await mountForm({
      device: SAMPLE_DEVICE,
      deviceTypes: SAMPLE_TYPES,
      orgOptions: [],
    })

    expect(wrapper.text()).toContain('编辑设备档案')
    expect(codeInput(wrapper).element.value).toBe('DEV-SMK-001')
    expect(nameInput(wrapper).element.value).toBe('1F大厅烟感A01')
    expect(wrapper.text()).toContain('灵敏度')
    expect(wrapper.text()).toContain('探测面积(㎡)')

    await findButton(wrapper, '确定').trigger('click')
    await flushPromises()

    expect(createDevice).not.toHaveBeenCalled()
    expect(updateDevice).toHaveBeenCalledTimes(1)
    expect(updateDevice.mock.calls[0][0]).toBe(SAMPLE_DEVICE.id)
    expect(updateDevice.mock.calls[0][1]).toMatchObject({
      device_code: 'DEV-SMK-001',
      attributes: { sensitivity: '高', detection_area: 60 },
    })
  })
})
