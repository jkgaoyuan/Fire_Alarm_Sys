<!--
巡检计划详情 (PlanDetail)
3.6-F1 配套组件
功能：展示计划详细信息和任务列表
-->
<template>
  <el-dialog
    v-model="visible"
    title="巡检计划详情"
    width="800px"
    @close="handleClose"
  >
    <el-descriptions v-if="planDetail" :column="2" border>
      <el-descriptions-item label="计划名称">{{ planDetail.plan_name }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="planDetail.is_enabled ? 'success' : 'info'">
          {{ planDetail.is_enabled ? '启用中' : '已停用' }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="所属区域">{{ planDetail.org_name || '-' }}</el-descriptions-item>
      <el-descriptions-item label="设备类型">{{ planDetail.device_type_name || '全部' }}</el-descriptions-item>
      <el-descriptions-item label="周期类型">{{ cycleTypeLabel(planDetail.cycle_type) }}</el-descriptions-item>
      <el-descriptions-item label="责任人">{{ planDetail.responsible_user_name || '-' }}</el-descriptions-item>
      <el-descriptions-item label="时间范围">
        {{ formatDate(planDetail.start_date) }} ~ {{ formatDate(planDetail.end_date || '长期') }}
      </el-descriptions-item>
      <el-descriptions-item label="创建时间">{{ formatDateTime(planDetail.created_at) }}</el-descriptions-item>
      
      <el-descriptions-item label="统计信息" :span="2">
        <div class="stats-info">
          <div>总任务数：{{ planDetail.total_tasks || 0 }}</div>
          <div>已完成：{{ planDetail.completed_tasks || 0 }} (完成率：{{ ((planDetail.completion_rate * 100) || 0).toFixed(1) }}%)</div>
          <div>漏检数：{{ planDetail.missed_tasks || 0 }}</div>
          <el-progress
            :percentage="(planDetail.completion_rate * 100 || 0).toFixed(1)"
            :color="getProgressColor(planDetail.completion_rate)"
          />
        </div>
      </el-descriptions-item>
    </el-descriptions>

    <el-divider>任务列表</el-divider>

    <el-table
      v-loading="taskLoading"
      :data="taskList"
      stripe
      border
    >
      <el-table-column prop="task_date" label="任务日期" width="120">
        <template #default="{ row }">
          {{ formatDate(row.task_date) }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="taskStatusType(row.status)">
            {{ taskStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="记录数" width="80" align="center">
        <template #default="{ row }">
          {{ row.records?.length || 0 }}
        </template>
      </el-table-column>
      <el-table-column prop="completed_at" label="完成时间" width="180">
        <template #default="{ row }">
          {{ formatDateTime(row.completed_at) }}
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="pagination.page"
      v-model:page-size="pagination.page_size"
      :total="pagination.total"
      layout="prev, pager, next"
      class="pagination"
      @current-change="loadTasks"
    />
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getInspectionPlanDetail, getInspectionTasks } from '@/api/inspection'

const props = defineProps({
  modelValue: Boolean,
  planId: {
    type: Number,
    default: null,
  },
})

const emit = defineEmits(['update:modelValue', 'success'])

const visible = ref(false)
const planDetail = ref(null)
const taskLoading = ref(false)
const taskList = ref([])

const pagination = reactive({ page: 1, page_size: 20, total: 0 })

watch(
  () => props.planId,
  (id) => {
    if (id) {
      loadDetail()
      loadTasks()
    }
  },
  { immediate: true }
)

watch(
  () => visible.value,
  (val) => {
    if (!val) {
      handleClose()
    }
  }
)

async function loadDetail() {
  try {
    const res = await getInspectionPlanDetail(props.planId)
    planDetail.value = res.data || {}
  } catch (err) {
    ElMessage.error(err.message || '加载详情失败')
  }
}

async function loadTasks() {
  if (!props.planId) return
  
  taskLoading.value = true
  try {
    const res = await getInspectionTasks({
      page: pagination.page,
      page_size: pagination.page_size,
    })
    const data = res.data || {}
    taskList.value = data.items || []
    pagination.total = data.total || 0
  } catch (err) {
    ElMessage.error('加载任务列表失败')
  } finally {
    taskLoading.value = false
  }
}

function handleClose() {
  visible.value = false
  emit('success')
}

// ==================== 辅助函数 ====================

function cycleTypeLabel(type) {
  const map = {
    daily: '每日',
    weekly: '每周',
    monthly: '每月',
    quarterly: '每季度',
    yearly: '每年',
  }
  return map[type] || type
}

function taskStatusLabel(status) {
  const map = {
    pending: '待执行',
    doing: '执行中',
    completed: '已完成',
    missed: '漏检',
  }
  return map[status] || status
}

function taskStatusType(status) {
  const map = {
    pending: '',
    doing: 'warning',
    completed: 'success',
    missed: 'danger',
  }
  return map[status] || ''
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  return dateStr.toString().slice(0, 10)
}

function formatDateTime(datetimeStr) {
  if (!datetimeStr) return '-'
  return datetimeStr.toString().replace('T', ' ').slice(0, 19)
}

function getProgressColor(rate) {
  if (rate >= 0.8) return '#67C23A'
  if (rate >= 0.5) return '#E6A23C'
  return '#F56C6C'
}
</script>

<style lang="scss" scoped>
.stats-info {
  line-height: 2;
}

.pagination {
  margin-top: 16px;
  justify-content: center;
}
</style>
