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
          <!-- 用 records_count（后端列表接口返回的计数），不能用 row.records?.length：
               后端列表接口从不填充 records 列表，那样写恒为 0。
               见 backend/app/schemas/inspection.py 的 InspectionTaskResponse 注释。 -->
          {{ row.records_count || 0 }}
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
import { computed, ref, reactive, watch } from 'vue'
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

// ⚠️ 必须是 computed 代理到 props.modelValue，**不能**写成 `const visible = ref(false)`：
// 那样写的话父组件传进来的 modelValue 只是被声明、从未被读，弹窗读的是另一个变量，
// 局部 ref 没有任何路径被置 true → 计划页点「详情」永远不弹，而且不报错。
// 2026-09-14 实测缺陷（同病三处：本文件 / RecordViewer / StatsDialog），
// 已加静态守卫 tests/dialogContract.spec.js。
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})
const planDetail = ref(null)
const taskLoading = ref(false)
const taskList = ref([])

const pagination = reactive({ page: 1, page_size: 20, total: 0 })

// 打开时才加载。原来监听 planId 且 immediate:true，会**在弹窗还关着的时候**就发请求；
// 而且 planId 与 modelValue 谁先到并不确定，改成监听 modelValue 更贴合「打开」这一时机。
// ⚠️ 必须 immediate：只监听「变化」的话，挂载时已打开（modelValue 初值 true）
// 永远不会触发回调，弹窗开着但详情与任务列表都是空的。
watch(
  () => props.modelValue,
  (val) => {
    if (val && props.planId) {
      pagination.page = 1
      loadDetail()
      loadTasks()
    }
  },
  { immediate: true }
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
      // 必须带 plan_id：不带的话拿到的是**全量任务**，
      // 计划 A 的详情里会列出计划 B 的任务（后端此前也不支持该参数，已一并补上）
      plan_id: props.planId,
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
  // 兜底必须是合法 type 或 undefined：空串会拼出不存在的 class `el-tag--`，
  // 既触发 Element Plus 的 prop 校验告警，又让「不想强调」的待执行标签
  // 回落到基础 .el-tag（蓝色）反而最显眼。default: 'primary' 只在 undefined
  // 时生效，拦不住显式空串。同 Task.vue / StatsDialog.vue。
  const map = {
    pending: undefined,
    doing: 'warning',
    completed: 'success',
    missed: 'danger',
  }
  return map[status]
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
