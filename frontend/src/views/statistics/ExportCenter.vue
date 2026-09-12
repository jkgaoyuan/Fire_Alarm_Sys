<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>导出中心</span>
          <el-button size="small" @click="router.push('/statistics/report')">返回</el-button>
        </div>
      </template>

      <!-- 任务列表 -->
      <el-table v-loading="loading" :data="tasks" border stripe>
        <el-table-column prop="task_no" label="任务编号" width="220" />
        <el-table-column label="类型" width="150">
          <template #default="{ row }">
            {{ taskTypeMap[row.task_type] || row.task_type }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTypeMap[row.status]" size="small">
              {{ statusMap[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="file_name" label="文件名" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="完成时间" width="180">
          <template #default="{ row }">
            {{ row.completed_at ? formatTime(row.completed_at) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'completed'"
              type="primary"
              link
              size="small"
              @click="downloadFile(row)"
            >
              下载
            </el-button>
            <el-button
              v-if="row.status === 'failed'"
              type="warning"
              link
              size="small"
              @click="retryExport(row)"
            >
              重试
            </el-button>
            <el-button
              v-if="row.status === 'pending' || row.status === 'running'"
              type="info"
              link
              size="small"
              disabled
            >
              处理中...
            </el-button>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty description="暂无导出任务">
            <el-button type="primary" size="small" @click="router.push('/statistics/report')">
              前往统计报表发起导出
            </el-button>
          </el-empty>
        </template>
      </el-table>

      <!-- 分页 -->
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="loadData"
        @current-change="loadData"
        style="margin-top: 20px;"
      />
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getMyExportTasks, downloadExportFile, createExportTask } from '@/api/reports'

const router = useRouter()

const loading = ref(false)
const tasks = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const taskTypeMap = {
  alarm_trend: '报警趋势',
  device_status: '设备状态',
  fault_top10: '故障TOP10',
  inspection: '巡检完成率',
  drill_report: '演练报告',
}

const statusMap = {
  pending: '待处理',
  running: '处理中',
  completed: '已完成',
  failed: '失败',
}

const statusTypeMap = {
  pending: 'info',
  running: 'warning',
  completed: 'success',
  failed: 'danger',
}

async function loadData() {
  loading.value = true
  try {
    const res = await getMyExportTasks({ page: page.value, page_size: pageSize.value })
    tasks.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (err) {
    ElMessage.error(err.message || '加载任务列表失败')
  } finally {
    loading.value = false
  }
}

async function downloadFile(row) {
  try {
    const blob = await downloadExportFile(row.id)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = row.file_name || 'export.xlsx'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('下载成功')
  } catch (err) {
    ElMessage.error(err.message || '下载失败')
  }
}

async function retryExport(row) {
  try {
    await ElMessageBox.confirm(
      `重新创建导出任务：${taskTypeMap[row.task_type] || row.task_type}？`,
      '确认重试',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await createExportTask({
      task_type: row.task_type,
      params: row.params || {},
      data: [],
      format: 'xlsx',
    })
    ElMessage.success('导出任务已重新创建')
    loadData()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || '重试失败')
    }
  }
}

function formatTime(timeStr) {
  if (!timeStr) return '-'
  const date = new Date(timeStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

onMounted(() => {
  loadData()

  // 轮询检查任务状态（每 5 秒）
  setInterval(() => {
    if (tasks.value.some(t => t.status === 'pending' || t.status === 'running')) {
      loadData()
    }
  }, 5000)
})
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
