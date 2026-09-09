import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/api/device', () => ({
  getDevices: vi.fn(),
  getDeviceTypes: vi.fn(),
  getDevice: vi.fn(),
  createDevice: vi.fn(),
  updateDevice: vi.fn(),
  deleteDevice: vi.fn(),
  retireDevice: vi.fn(),
  getDeviceHistory: vi.fn(),
  importDevices: vi.fn(),
  downloadImportTemplate: vi.fn(),
}))

vi.mock('@/api/organization', () => ({
  getOrganizations: vi.fn(),
  getOrganizationTree: vi.fn(),
}))

// MessageBox 弹窗渲染在组件树之外，替换为可控 mock，其余导出保持原样
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessageBox: {
      ...actual.ElMessageBox,
      prompt: vi.fn(),
      confirm: vi.fn(),
    },
  }
})

import { ElMessageBox } from 'element-plus'
import {
  deleteDevice,
  getDevices as getDevicesMock,
  getDeviceTypes as getDeviceTypesMock,
  retireDevice,
} from '@/api/device'
import { getOrganizationTree as getOrganizationTreeMock } from '@/api/organization'
import Archive from '../Archive.vue'
import {
  findButton,
  mountOptions,
  visibleButtonTexts,
  SAMPLE_DEVICE,
  SAMPLE_ORG_TREE,
  SAMPLE_TYPES,
} from './mount'

const ALL_PERMS = ['device:view', 'device:create', 'device:update', 'device:retire', 'device:delete']

function mockList(items = [SAMPLE_DEVICE], total = items.length) {
  getDevicesMock.mockResolvedValue({ data: { items, total, page: 1, page_size: 20 } })
}

async function mountArchive(permissions = ALL_PERMS) {
  const wrapper = mount(Archive, mountOptions(permissions))
  await flushPromises()
  return wrapper
}

describe('Archive.vue 设备档案列表', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockList()
    getDeviceTypesMock.mockResolvedValue({ data: SAMPLE_TYPES })
    getOrganizationTreeMock.mockResolvedValue({ data: SAMPLE_ORG_TREE })
  })

  it('挂载后加载列表并渲染设备行', async () => {
    const wrapper = await mountArchive()

    expect(getDevicesMock).toHaveBeenCalledTimes(1)
    expect(getDeviceTypesMock).toHaveBeenCalledTimes(1)
    expect(getOrganizationTreeMock).toHaveBeenCalledTimes(1)

    const rows = wrapper.findAll('.el-table__body-wrapper .el-table__row')
    expect(rows).toHaveLength(1)
    expect(wrapper.text()).toContain('DEV-SMK-001')
    expect(wrapper.text()).toContain('1F大厅烟感A01')
    expect(wrapper.text()).toContain('正常')
    expect(wrapper.text()).toContain('共 1 台')
  })

  it('关键字搜索重置页码并带上筛选参数', async () => {
    const wrapper = await mountArchive()
    getDevicesMock.mockClear()

    await wrapper.find('input[placeholder="设备编码或名称"]').setValue('烟感')
    await findButton(wrapper, '搜索').trigger('click')
    await flushPromises()

    expect(getDevicesMock).toHaveBeenCalledTimes(1)
    expect(getDevicesMock.mock.calls[0][0]).toMatchObject({
      keyword: '烟感',
      page: 1,
      page_size: 20,
      include_retired: false,
    })
  })

  it('「显示已退役」开关切换 include_retired', async () => {
    const wrapper = await mountArchive()
    getDevicesMock.mockClear()

    await wrapper.find('.el-switch').trigger('click')
    await flushPromises()

    expect(getDevicesMock).toHaveBeenCalledTimes(1)
    expect(getDevicesMock.mock.calls[0][0].include_retired).toBe(true)
  })

  it('分页切换与每页条数变更都会重新请求', async () => {
    const wrapper = await mountArchive()
    getDevicesMock.mockClear()

    const pagination = wrapper.findComponent({ name: 'ElPagination' })
    pagination.vm.$emit('current-change', 3)
    await flushPromises()
    expect(getDevicesMock.mock.calls[0][0].page).toBe(3)

    getDevicesMock.mockClear()
    pagination.vm.$emit('size-change', 50)
    await flushPromises()
    expect(getDevicesMock.mock.calls[0][0]).toMatchObject({ page: 1, page_size: 50 })
  })

  it('已退役行加灰置样式且不显示编辑/退役按钮', async () => {
    mockList([{ ...SAMPLE_DEVICE, status: 'retired' }])
    const wrapper = await mountArchive()

    const row = wrapper.find('.el-table__row')
    expect(row.classes()).toContain('retired-row')
    expect(row.text()).toContain('已退役')

    const actions = row.findAll('button').map((btn) => btn.text())
    expect(actions).toContain('查看')
    expect(actions).toContain('删除')
    expect(actions).not.toContain('编辑')
    expect(actions).not.toContain('退役')
  })

  it('退役需填写原因，成功后调用接口并刷新列表', async () => {
    ElMessageBox.prompt.mockResolvedValue({ value: '设备老化，更换新机' })
    retireDevice.mockResolvedValue({ data: { ...SAMPLE_DEVICE, status: 'retired' } })
    const wrapper = await mountArchive()
    getDevicesMock.mockClear()

    await findButton(wrapper, '退役').trigger('click')
    await flushPromises()

    expect(ElMessageBox.prompt).toHaveBeenCalledTimes(1)
    expect(retireDevice).toHaveBeenCalledWith(1, { reason: '设备老化，更换新机' })
    expect(getDevicesMock).toHaveBeenCalledTimes(1)
  })

  it('取消退役确认时不调用退役接口', async () => {
    ElMessageBox.prompt.mockRejectedValue('cancel')
    const wrapper = await mountArchive()

    await findButton(wrapper, '退役').trigger('click')
    await flushPromises()

    expect(retireDevice).not.toHaveBeenCalled()
  })

  it('无 device:retire 权限时退役按钮隐藏', async () => {
    const wrapper = await mountArchive(ALL_PERMS.filter((p) => p !== 'device:retire'))
    const actions = visibleButtonTexts(wrapper.find('.el-table__row'))
    expect(actions).toContain('编辑')
    expect(actions).not.toContain('退役')
  })

  it('无 device:delete 权限时删除按钮隐藏', async () => {
    const wrapper = await mountArchive(['device:view', 'device:update'])
    const visible = visibleButtonTexts(wrapper.find('.el-table__row'))
    expect(visible).toContain('编辑')
    expect(visible).not.toContain('删除')
    expect(deleteDevice).not.toHaveBeenCalled()
  })
})
