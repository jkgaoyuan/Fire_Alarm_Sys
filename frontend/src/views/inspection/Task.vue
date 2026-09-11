<!--
巡检任务与记录填报 (Task.vue)
3.6-F2
功能：
- 任务列表查询（分页 + 筛选）
- 执行巡检并提交记录
- 查看历史巡检记录
权限码：inspection:view/execute
-->
<template>
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="search-card" shadow="never">
      <el-form :model="searchForm" inline>
        <el-form-item label="任务日期">
          <el-date-picker
            v-model="searchForm.date_range"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 280px"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="searchForm.status"
            placeholder="全部状态"
            clearable
            style="width: 160px"
          >
            <el-option label="待执行" value="pending" />
            <el-option label="执行中" value="doing" />
            <el-option label="已完成" value="completed" />
            <el-option label="漏检" value="missed" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 任务列表 -->
    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>巡检任务（共 {{ pagination.total }} 个）</span>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="taskList"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="task_date" label="任务日期" width="120">
          <template #default="{ row }">
            <el-tag :type="isToday(row.task_date) ? 'danger' : ''">
              {{ formatDate(row.task_date) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="plan_name" label="计划名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="cycle_type" label="周期" width="100">
          <template #default="{ row }">
            {{ cycleTypeLabel(row.cycle_type) }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="taskStatusType(row.status)">
              {{ taskStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="records_count" label="已记录数" width="100" align="center">
          <template #default="{ row }">
            {{ row.records_count || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" align="center" fixed="right">
          <template #default="{ row }">
            <PermissionButton
              permission="inspection:view"
              link
              type="primary"
              @click="handleViewRecords(row)"
            >
              查看记录
            </PermissionButton>
            <PermissionButton
              permission="inspection:execute"
              link
              type="success"
              :disabled="row.status !== 'pending' && row.status !== 'doing'"
              @click="handleExecute(row)"
            >
              执行巡检
            </PermissionButton>
            <PermissionButton
              permission="inspection:stat"
              link
              type="info"
              @click="handleShowStats(row)"
            >
              统计信息
            </PermissionButton>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :page-sizes="[10, 20, 50]"
        :total="pagination.total"
        layout="total, sizes, prev, pager, next, jumper"
        class="pagination"
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </el-card>

    <!-- 执行巡检弹窗 -->
    <ExecutionDialog
      v-model="execVisible"
      :task-id="currentTaskId"
      @success="loadTasks"
    />

    <!-- 记录查看弹窗 -->
    <RecordViewer
      v-model="viewVisible"
      :task-id="currentTaskId"
    />

    <!-- 统计信息弹窗 -->
    <StatsDialog
      v-model="statsVisible"
      :task-id="currentTaskId"
    />
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import PermissionButton from '@/components/PermissionButton.vue'
import ExecutionDialog from './ExecutionDialog.vue'
import RecordViewer from './RecordViewer.vue'
import StatsDialog from './StatsDialog.vue'
import { getInspectionTasks } from '@/api/inspection'

const loading = ref(false)
const taskList = ref([])

const searchForm = reactive({
  date_range: [],
  status: null,
})

const pagination = reactive({ page: 1, page_size: 20, total: 0 })

// Dialogs
const execVisible = ref(false)
const viewVisible = ref(false)
const statsVisible = ref(false)
const currentTaskId = ref(null)

onMounted(() => {
  loadTasks()
})

// ==================== 数据加载 ====================

async function loadTasks() {
  loading.value = true
  try {
    const [start, end] = searchForm.date_range || []
    
    const res = await getInspectionTasks({
      page: pagination.page,
      page_size: pagination.page_size,
      start_date: start || undefined,
      end_date: end || undefined,
      status: searchForm.status || undefined,
    })
    
    const data = res.data || {}
    taskList.value = data.items || []
    pagination.total = data.total || 0
  } catch (err) {
    ElMessage.error(err.message || '加载任务列表失败')
  } finally {
    loading.value = false
  }
}

// ==================== 筛选与分页 ====================

function handleSearch() {
  pagination.page = 1
  loadTasks()
}

function handleReset() {
  searchForm.date_range = []
  searchForm.status = null
  handleSearch()
}

function handleSizeChange(size) {
  pagination.page_size = size
  pagination.page = 1
  loadTasks()
}

function handlePageChange(page) {
  pagination.page = page
  loadTasks()
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
  const d = new Date(dateStr)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function isToday(dateStr) {
  const today = new Date()
  const d = new Date(dateStr)
  return (
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate()
  )
}

// ==================== 操作 ====================

function handleExecute(row) {
  currentTaskId.value = row.id
  execVisible.value = true
}

function handleViewRecords(row) {
  currentTaskId.value = row.id
  viewVisible.value = true
}

function handleShowStats(row) {
  currentTaskId.value = row.id
  statsVisible.value = true
}
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20px;
}

.search-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-card {
  .pagination {
    margin-top: 16px;
    justify-content: flex-end;
  }
}
</style>
