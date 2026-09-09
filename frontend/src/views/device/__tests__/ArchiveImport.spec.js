import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/api/device', () => ({
  importDevices: vi.fn(),
  downloadImportTemplate: vi.fn(),
}))

import { downloadImportTemplate, importDevices } from '@/api/device'
import ArchiveImport from '../ArchiveImport.vue'
import { findButton, overlayOptions } from './mount'

const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

async function mountImport() {
  const wrapper = mount(ArchiveImport, overlayOptions())
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  return wrapper
}

/** 走 ElUpload 真实的 handleStart → on-change 链路 */
async function selectFile(wrapper, name = '设备档案.xlsx') {
  const file = new File(['mock'], name, { type: XLSX_MIME })
  wrapper.findComponent({ name: 'ElUpload' }).vm.handleStart(file)
  await flushPromises()
  return file
}

describe('ArchiveImport.vue 批量导入', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('未选择文件时导入按钮禁用', async () => {
    const wrapper = await mountImport()

    expect(wrapper.text()).toContain('批量导入设备档案')
    expect(findButton(wrapper, '开始导入').attributes('disabled')).toBeDefined()

    await selectFile(wrapper)

    expect(findButton(wrapper, '开始导入').attributes('disabled')).toBeUndefined()
  })

  it('上传成功后展示汇总并通知父级刷新', async () => {
    importDevices.mockResolvedValue({
      data: { total: 7, success: 7, failed: 0, rolled_back: false, failures: [] },
    })
    const wrapper = await mountImport()
    const file = await selectFile(wrapper)

    await findButton(wrapper, '开始导入').trigger('click')
    await flushPromises()

    expect(importDevices).toHaveBeenCalledTimes(1)
    expect(importDevices.mock.calls[0][0]).toBe(file)
    expect(wrapper.text()).toContain('共 7 行，成功 7 行，失败 0 行')
    expect(wrapper.emitted('success')).toHaveLength(1)
  })

  it('部分失败时列出失败行明细并保留已导入数据', async () => {
    importDevices.mockResolvedValue({
      data: {
        total: 7,
        success: 4,
        failed: 3,
        rolled_back: false,
        failures: [
          { row: 3, device_code: 'DEV-SMK-001', reason: '设备编码已存在: DEV-SMK-001' },
          { row: 5, device_code: 'DEV-X', reason: '设备类型编码不存在: xxx' },
        ],
      },
    })
    const wrapper = await mountImport()
    await selectFile(wrapper)

    await findButton(wrapper, '开始导入').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('共 7 行，成功 4 行，失败 3 行')
    expect(wrapper.find('.failure-table').exists()).toBe(true)
    expect(wrapper.text()).toContain('设备编码已存在: DEV-SMK-001')
    expect(wrapper.emitted('success')).toHaveLength(1)
  })

  it('整批回滚时提示未写入任何数据', async () => {
    importDevices.mockResolvedValue({
      data: {
        total: 2,
        success: 0,
        failed: 2,
        rolled_back: true,
        failures: [{ row: 1, device_code: 'DEV-A', reason: '缺少必填列' }],
      },
    })
    const wrapper = await mountImport()
    await selectFile(wrapper)

    await findButton(wrapper, '开始导入').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('失败 2 行已超过阈值，整批回滚未写入任何数据')
    expect(wrapper.emitted('success')).toBeUndefined()
  })

  it('下载模板时以 Blob 触发浏览器下载', async () => {
    downloadImportTemplate.mockResolvedValue(new Blob(['x'], { type: XLSX_MIME }))
    const clicks = []
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function click() {
        clicks.push(this.download)
      })
    // jsdom 未实现 ObjectURL，只能直接打桩
    const createSpy = vi.fn(() => 'blob:mock')
    const revokeSpy = vi.fn()
    window.URL.createObjectURL = createSpy
    window.URL.revokeObjectURL = revokeSpy

    try {
      const wrapper = await mountImport()
      await findButton(wrapper, '下载导入模板').trigger('click')
      await flushPromises()

      expect(downloadImportTemplate).toHaveBeenCalledTimes(1)
      expect(clicks).toEqual(['消防设备档案导入模板.xlsx'])
      expect(revokeSpy).toHaveBeenCalledWith('blob:mock')
    } finally {
      clickSpy.mockRestore()
      delete window.URL.createObjectURL
      delete window.URL.revokeObjectURL
    }
  })
})
