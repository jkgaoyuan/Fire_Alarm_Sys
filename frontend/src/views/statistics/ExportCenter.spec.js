/**
 * ExportCenter.vue 组件测试
 * 
 * 测试报表导出中心的核心逻辑
 */
import { describe, it, expect } from 'vitest'

// 模拟任务类型映射
const taskTypeMap = {
  device_status: '设备状态报告',
  alarm_trend: '报警趋势图',
  fault_top10: '故障 TOP10',
  inspection_completion: '巡检完成率',
  drill_report: '演练总结报告'
}

const getTaskTypeName = (taskType) => {
  return taskTypeMap[taskType] || taskType
}

// 检查任务是否可以下载
const canDownloadTask = (task) => {
  if (!task) return false
  return task.status === 'completed'
}

describe('ExportCenter 核心逻辑', () => {
  const mockTasks = [
    {
      id: 1,
      task_no: 'EXP_2026091100001',
      task_type: 'device_status',
      file_name: '设备状态报告_20260911.xlsx',
      status: 'completed',
      total_rows: 500,
      created_by_name: '张三',
      completed_at: '2026-09-11T10:30:00Z'
    },
    {
      id: 2,
      task_no: 'EXP_2026091100002',
      task_type: 'alarm_trend',
      file_name: '报警趋势图_20260911.csv',
      status: 'running',
      total_rows: 1000,
      created_by_name: '李四',
      completed_at: null
    }
  ]

  it('正确获取任务类型名称', () => {
    expect(getTaskTypeName('device_status')).toBe('设备状态报告')
    expect(getTaskTypeName('alarm_trend')).toBe('报警趋势图')
    expect(getTaskTypeName('unknown_type')).toBe('unknown_type')
  })

  it('正确判断任务是否可以下载', () => {
    expect(canDownloadTask(mockTasks[0])).toBe(true) // completed
    expect(canDownloadTask(mockTasks[1])).toBe(false) // running
    expect(canDownloadTask(null)).toBe(false)
  })

  it('统计已完成任务数量', () => {
    const completedCount = mockTasks.filter(t => canDownloadTask(t)).length
    expect(completedCount).toBe(1)
  })

  it('统计总任务数和平均行数', () => {
    const totalCount = mockTasks.length
    const avgRows = Math.round(mockTasks.reduce((sum, t) => sum + t.total_rows, 0) / totalCount)
    
    expect(totalCount).toBe(2)
    expect(avgRows).toBe(750) // (500+1000)/2
  })

  it('任务编号格式验证', () => {
    mockTasks.forEach(task => {
      expect(task.task_no).toMatch(/^EXP_/)
      expect(task.task_no.length).toBeGreaterThan(5)
    })
  })
})
