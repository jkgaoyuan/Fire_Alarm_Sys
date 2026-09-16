import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/api/device', () => ({
  getDevice: vi.fn(),
  getDeviceHistory: vi.fn(),
}))

import { getDevice, getDeviceHistory } from '@/api/device'
import ArchiveDetail from '../ArchiveDetail.vue'
import { overlayOptions, SAMPLE_DEVICE, SAMPLE_TYPES } from './mount'

const HISTORY = {
  device_id: 1,
  device_code: 'DEV-SMK-001',
  total: 2,
  items: [
    {
      category: 'status_change',
      title: '状态变更：正常 → 已退役',
      detail: '设备老化，整机更换',
      operator: 'admin',
      created_at: '2026-09-08T11:20:00',
    },
    {
      category: 'status_change',
      title: '建档：DEV-SMK-001',
      detail: '初始状态：正常',
      operator: 'chief',
      created_at: '2026-03-15T09:00:00',
    },
  ],
}

/**
 * 四类数据源齐全的载荷，供页签过滤与配色用例使用。
 * 单列一份而不是改造上面的 `HISTORY`，是为了不去搅动那些与本次无关的既有断言。
 */
const HISTORY_FULL = {
  device_id: 1,
  device_code: 'DEV-SMK-001',
  total: 5,
  items: [
    {
      category: 'inspection',
      title: '巡检：异常',
      detail: '压力表读数偏低',
      operator: '张三',
      created_at: '2026-09-08T11:40:00',
    },
    {
      category: 'repair',
      title: '维修：RO-ABC123（维修中）',
      detail: '泵体异响',
      operator: '李四',
      created_at: '2026-09-08T11:30:00',
    },
    {
      category: 'alarm',
      title: '报警：火警',
      detail: '3 层东侧',
      operator: '值班员',
      created_at: '2026-09-08T11:25:00',
    },
    {
      category: 'status_change',
      title: '状态变更：正常 → 已退役',
      detail: '设备老化，整机更换',
      operator: 'admin',
      created_at: '2026-09-08T11:20:00',
    },
    {
      category: 'status_change',
      title: '建档：DEV-SMK-001',
      detail: '初始状态：正常',
      operator: 'chief',
      created_at: '2026-03-15T09:00:00',
    },
  ],
}

async function mountDetail(props = {}) {
  const wrapper = mount(ArchiveDetail, overlayOptions({ deviceTypes: SAMPLE_TYPES, ...props }))
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  return wrapper
}

describe('ArchiveDetail.vue 设备档案详情', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getDevice.mockResolvedValue({ data: SAMPLE_DEVICE })
    getDeviceHistory.mockResolvedValue({ data: HISTORY })
  })

  it('打开时并行加载档案与历史并渲染字段', async () => {
    const wrapper = await mountDetail({ deviceId: SAMPLE_DEVICE.id })

    expect(getDevice).toHaveBeenCalledWith(SAMPLE_DEVICE.id)
    expect(getDeviceHistory).toHaveBeenCalledWith(SAMPLE_DEVICE.id, { limit: 200 })

    const text = wrapper.text()
    expect(text).toContain('DEV-SMK-001')
    expect(text).toContain('1F大厅烟感A01')
    expect(text).toContain('烟感探测器')
    expect(text).toContain('总部大楼')
    expect(text).toContain('正常')
    expect(text).toContain('90 天')
    expect(text).toContain('Honeywell / XLS-PS')
    expect(text).toContain('2025-03-15')
    expect(text).toContain('(120.5, 340.2)')
    expect(text).toContain('chief')
  })

  it('扩展属性按类型 schema 显示中文标签', async () => {
    const wrapper = await mountDetail({ deviceId: 1 })

    expect(wrapper.text()).toContain('灵敏度：高')
    expect(wrapper.text()).toContain('探测面积(㎡)：60')
    expect(wrapper.findAll('.attribute-tag')).toHaveLength(2)
  })

  it('历史记录按时间倒序展示变更内容与操作人', async () => {
    const wrapper = await mountDetail({ deviceId: 1 })

    const entries = wrapper.findAll('.el-timeline-item')
    expect(entries).toHaveLength(2)
    expect(entries[0].text()).toContain('状态变更：正常 → 已退役')
    expect(entries[0].text()).toContain('设备老化，整机更换')
    expect(entries[0].text()).toContain('操作人：admin')
    expect(entries[0].text()).toContain('2026-09-08 11:20:00')
    expect(entries[1].text()).toContain('建档：DEV-SMK-001')
  })

  it('巡检 / 维修页签展示真数据并按类别过滤（不再是「尚未上线」占位）', async () => {
    // 3.4 / 3.7 已交付，后端已把两类记录聚合进时间轴，占位机制随接入移除
    getDeviceHistory.mockResolvedValue({ data: HISTORY_FULL })
    const wrapper = await mountDetail({ deviceId: 1 })

    const tabs = wrapper.findAll('.el-tabs__item').map((tab) => tab.text())
    expect(tabs).toEqual(
      expect.arrayContaining(['历史记录', '状态轨迹', '巡检记录', '维修记录'])
    )
    // 占位文案必须彻底消失
    expect(wrapper.text()).not.toContain('尚未上线')

    // 「历史记录」= 全部四类
    expect(wrapper.text()).toContain('巡检：异常')
    expect(wrapper.text()).toContain('维修：RO-ABC123')
    expect(wrapper.text()).toContain('报警：火警')
    expect(wrapper.text()).toContain('建档：DEV-SMK-001')

    // 「巡检记录」只剩巡检 —— 这条同时钉住 visibleHistory 的按类别过滤
    await wrapper.findAll('.el-tabs__item').find((t) => t.text() === '巡检记录').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('巡检：异常')
    expect(wrapper.text()).not.toContain('维修：RO-ABC123')
    expect(wrapper.text()).not.toContain('报警：火警')
    expect(wrapper.text()).not.toContain('建档：DEV-SMK-001')

    // 「维修记录」只剩维修
    await wrapper.findAll('.el-tabs__item').find((t) => t.text() === '维修记录').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('维修：RO-ABC123')
    expect(wrapper.text()).not.toContain('巡检：异常')
  })

  it('时间轴按类别分色 —— 火警不得渲染成表示「成功」的绿色', async () => {
    getDeviceHistory.mockResolvedValue({ data: HISTORY_FULL })
    const wrapper = await mountDetail({ deviceId: 1 })

    // el-timeline-item 把 type 映射到节点修饰类上，按 DOM 断言而不依赖组件内部
    const nodes = wrapper.findAll('.el-timeline-item__node')
    const nodeClassOf = (title) => {
      const row = wrapper
        .findAll('.el-timeline-item')
        .find((li) => li.text().includes(title))
      return row.find('.el-timeline-item__node').classes().join(' ')
    }

    expect(nodes).toHaveLength(5)
    expect(nodeClassOf('报警：火警')).toContain('danger')
    expect(nodeClassOf('巡检：异常')).toContain('success')
    expect(nodeClassOf('维修：RO-ABC123')).toContain('warning')
    expect(nodeClassOf('建档：')).toContain('primary')
  })

  it('档案接口失败时显示空态而不是抛错', async () => {
    getDevice.mockRejectedValue(new Error('设备不存在'))
    const wrapper = await mountDetail({ deviceId: 999 })

    expect(wrapper.text()).toContain('设备不存在或已被删除')
    expect(wrapper.find('.el-descriptions').exists()).toBe(false)
  })

  /**
   * 回归：抽屉**开着**的时候换 deviceId，必须重新取数。
   *
   * 这正是「大屏电子地图点击设备 → 跳设备详情 → 提示设备不存在或已被删除，
   * 而设备其实存在」的根因：`/device/archive?detail=1` → `?detail=2` 是
   * **同一条路由换 query**，Vue 复用组件不重新挂载；而加载只挂在抽屉的
   * `@open` 上，`open` 只在「关→开」跳变时触发 —— deviceId 变了但抽屉一直开着，
   * `open` 不再触发，`loadAll()` 从不执行，`device` 保持 null，
   * 于是渲染出 v-else 的「设备不存在或已被删除」，**请求压根没发出去**。
   */
  /**
   * **主场景回归**：挂载时抽屉就已经是打开的（不存在任何「关→开」跳变）。
   *
   * 大屏点设备跳 `/device/archive?detail=X` 时，`Archive.vue` 的
   * `watch(() => route.query.detail, ..., { immediate: true })` 在 **setup 里同步**
   * 就把 `detailVisible` 置为 true，于是 `el-drawer` 首渲染即打开 ——
   * 真实的 el-drawer 不会为此发 `open` 事件。若加载只挂在 `@open` 上，
   * `loadAll()` 就永远不执行，页面渲染出「设备不存在或已被删除」，而设备其实存在。
   *
   * 注意本文件原有的 `mountDetail()` 刻意**先 modelValue: false 再 setProps(true)**，
   * 正好绕开了这条路径 —— 所以这个缺陷长期没被看见。
   */
  it('挂载时抽屉已打开也要加载（大屏跳转的主场景）', async () => {
    const wrapper = mount(
      ArchiveDetail,
      overlayOptions({ deviceTypes: SAMPLE_TYPES, modelValue: true, deviceId: 3 })
    )
    await flushPromises()

    expect(getDevice).toHaveBeenCalledWith(3)
    expect(getDeviceHistory).toHaveBeenCalledWith(3, { limit: 200 })
    expect(wrapper.text()).toContain('DEV-SMK-001')
  })

  it('抽屉关着时不预取，等打开再加载（避免白发请求）', async () => {
    mount(ArchiveDetail, overlayOptions({ deviceTypes: SAMPLE_TYPES, deviceId: 3 }))
    await flushPromises()
    expect(getDevice).not.toHaveBeenCalled()
  })

  it('抽屉开着时切换 deviceId 会重新取数', async () => {
    const wrapper = await mountDetail({ deviceId: 1 })
    expect(getDevice).toHaveBeenCalledWith(1)
    // `@open` 与 deviceId 的 watch 不能各发一次 —— 打开只加载一次
    expect(getDevice).toHaveBeenCalledTimes(1)

    // 模拟 ?detail=1 → ?detail=2：组件复用，modelValue 始终为 true，无「关→开」跳变
    await wrapper.setProps({ deviceId: 2 })
    await flushPromises()

    expect(getDevice).toHaveBeenCalledWith(2)
    expect(getDeviceHistory).toHaveBeenCalledWith(2, { limit: 200 })
    expect(getDevice).toHaveBeenCalledTimes(2)
  })
})
