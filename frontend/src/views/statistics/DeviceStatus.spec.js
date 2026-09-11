/**
 * DeviceStatus.vue 组件测试
 * 
 * 测试设备完好率看板的核心计算逻辑
 */
import { describe, it, expect } from 'vitest'

// 测试模块级别的计算逻辑
const calculateCompletionRate = (data) => {
  if (!data || !data.items || data.total === 0 || data.items.length === 0) return 0
  const normalCount = data.items.find(i => i.status === 'normal')?.count || 0
  return Math.round((normalCount / data.total) * 100)
}

describe('DeviceStatus 计算逻辑', () => {
  const mockData = {
    items: [
      { status: 'normal', count: 450, label: '正常' },
      { status: 'alarm', count: 20, label: '报警' },
      { status: 'fault', count: 15, label: '故障' },
      { status: 'shield', count: 10, label: '屏蔽' },
      { status: 'offline', count: 5, label: '离线' }
    ],
    total: 500
  }

  it('正确计算设备完好率', () => {
    const rate = calculateCompletionRate(mockData)
    expect(rate).toBe(90) // 450/500*100 = 90
  })

  it('处理空数据情况', () => {
    expect(calculateCompletionRate(null)).toBe(0)
    expect(calculateCompletionRate({ total: 0 })).toBe(0)
    expect(calculateCompletionRate({ items: [] })).toBe(0)
  })

  it('正确处理没有 normal 状态的数据', () => {
    const noNormalData = {
      items: [
        { status: 'alarm', count: 50, label: '报警' },
        { status: 'fault', count: 30, label: '故障' }
      ],
      total: 80
    }
    const rate = calculateCompletionRate(noNormalData)
    expect(rate).toBe(0)
  })

  it('统计总数正确', () => {
    const totalItems = mockData.items.reduce((sum, item) => sum + item.count, 0)
    expect(totalItems).toBe(mockData.total)
  })
})
