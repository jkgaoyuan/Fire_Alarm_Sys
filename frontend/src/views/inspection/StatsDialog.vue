<!--
统计信息弹窗 (StatsDialog)
3.6-F2 配套组件
功能：展示任务的统计数据
-->
<template>
  <el-dialog
    v-model="visible"
    title="任务统计信息"
    width="600px"
  >
    <div v-if="stats" class="stats-content">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="任务日期">{{ formatDate(taskData.task_date) }}</el-descriptions-item>
        <el-descriptions-item label="所属计划">{{ taskData.plan_name }}</el-descriptions-item>
        <el-descriptions-item label="周期类型">{{ cycleTypeLabel(taskData.cycle_type) }}</el-descriptions-item>
        <el-descriptions-item label="当前状态">
          <el-tag :type="taskStatusType(taskData.status)">
            {{ taskStatusLabel(taskData.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="已记录设备数">{{ recordsCount || 0 }}个</el-descriptions-item>
        <el-descriptions-item label="异常次数">{{ abnormalCount || 0 }}次</el-descriptions-item>
        <el-descriptions-item label="完成率">{{ completionRate }}%</el-descriptions-item>
      </el-descriptions>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { getInspectionTasks } from '@/api/inspection'

const props = defineProps({
  modelValue: Boolean,
  taskId: {
    type: Number,
    default: null,
  },
})

const emit = defineEmits(['update:modelValue'])

const visible = ref(false)
const taskData = ref(null)
const stats = ref(null)
const recordsCount = ref(0)
const abnormalCount = ref(0)
const completionRate = ref(0)

watch(
  () => visible.value,
  (val) => {
    if (val && props.taskId) {
      loadTaskData()
    }
  }
)

async function loadTaskData() {
  try {
    // TODO: Implement task detail API if needed
    // For now, show placeholder data
    taskData.value = {
      task_date: new Date().toISOString(),
      plan_name: '示例计划',
      cycle_type: 'daily',
      status: 'pending',
    }
    
    stats.value = {}
  } catch (err) {
    console.error('加载统计信息失败:', err)
  }
}

function handleClose() {
  visible.value = false
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  return dateStr.toString().slice(0, 10)
}

function cycleTypeLabel(type) {
  const map = { daily: '每日', weekly: '每周', monthly: '每月', quarterly: '每季度', yearly: '每年' }
  return map[type] || type
}

function taskStatusLabel(status) {
  const map = { pending: '待执行', doing: '执行中', completed: '已完成', missed: '漏检' }
  return map[status] || status
}

function taskStatusType(status) {
  const map = { pending: '', doing: 'warning', completed: 'success', missed: 'danger' }
  return map[status] || ''
}
</script>

<style lang="scss" scoped>
.stats-content {
  line-height: 2;
}
</style>
