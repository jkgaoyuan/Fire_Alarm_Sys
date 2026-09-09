import { describe, it, expect } from 'vitest'
import {
  DEVICE_STATUS_OPTIONS,
  deviceStatusLabel,
  deviceStatusType,
  emptyAttributes,
  isTerminalStatus,
  mergeAttributes,
  resolveAttributeFields,
  stripEmptyChildren,
} from '../device'

const SCHEMA = {
  sensitivity: { label: '灵敏度', type: 'select', options: ['高', '中', '低'] },
  detection_area: { label: '探测面积(㎡)', type: 'number' },
  serial_no: { label: '序列号', type: 'string' },
  enabled: { label: '启用', type: 'boolean' },
}

describe('utils/device.js', () => {
  it('状态标签覆盖后端全部枚举值', () => {
    expect(DEVICE_STATUS_OPTIONS.map((item) => item.value)).toEqual([
      'normal',
      'alarm',
      'fault',
      'shield',
      'offline',
      'retired',
    ])
    expect(deviceStatusLabel('fault')).toBe('故障')
    expect(deviceStatusLabel('retired')).toBe('已退役')
    expect(deviceStatusLabel('unknown_status')).toBe('unknown_status')
    expect(deviceStatusLabel(null)).toBe('-')
    expect(deviceStatusType('alarm')).toBe('danger')
    expect(deviceStatusType('unknown_status')).toBe('info')
  })

  it('仅已退役为终态', () => {
    expect(isTerminalStatus('retired')).toBe(true)
    expect(isTerminalStatus('offline')).toBe(false)
  })

  it('去掉叶子节点的空 children', () => {
    const tree = [
      {
        id: 1,
        org_name: '根',
        children: [
          { id: 2, org_name: '子', children: [] },
          { id: 3, org_name: '子2', children: [{ id: 4, org_name: '孙', children: [] }] },
        ],
      },
    ]
    const [root] = stripEmptyChildren(tree)
    expect('children' in root).toBe(true)
    expect('children' in root.children[0]).toBe(false)
    expect(root.children[1].children[0]).toEqual({ id: 4, org_name: '孙' })
    expect(stripEmptyChildren(undefined)).toEqual([])
  })

  it('number 类型扩展属性用 null 占位，其余用空串', () => {
    expect(emptyAttributes(SCHEMA)).toEqual({
      sensitivity: '',
      detection_area: null,
      serial_no: '',
      enabled: '',
    })
    expect(emptyAttributes(undefined)).toEqual({})
  })

  it('合并已有属性时补齐 schema 键并保留原值', () => {
    expect(mergeAttributes(SCHEMA, { detection_area: 60, extra: 'x' })).toEqual({
      sensitivity: '',
      detection_area: 60,
      serial_no: '',
      enabled: '',
      extra: 'x',
    })
    expect(mergeAttributes(null, null)).toEqual({})
  })

  it('解析扩展属性字段时降级不支持的类型', () => {
    const fields = resolveAttributeFields(SCHEMA)
    expect(fields).toHaveLength(4)
    expect(fields[0]).toEqual({
      key: 'sensitivity',
      label: '灵敏度',
      type: 'select',
      options: ['高', '中', '低'],
    })
    expect(fields[1].type).toBe('number')
    expect(fields[3].type).toBe('string')
    expect(resolveAttributeFields(undefined)).toEqual([])
    expect(resolveAttributeFields({ sn: {} })).toEqual([
      { key: 'sn', label: 'sn', type: 'string', options: [] },
    ])
  })
})
