<template>
  <div class="page-container emergency-list">
    <el-card class="search-card" shadow="never">
      <el-form :model="filters" inline>
        <el-form-item label="事件编号">
          <el-input v-model="filters.event_no" placeholder="请输入" clearable style="width: 200px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 150px">
            <el-option v-for="item in STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="区域">
          <el-cascader
            v-model="filters.org_id"
            :options="orgOptions"
            :props="cascaderProps"
            placeholder="全部区域"
            clearable
            style="width: 200px"
          />
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filters.range"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 380px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>应急事件（共 {{ pagination.total }} 条）</span>
        </div>
      </template>

      <el-table v-loading="loading" :data="rows" stripe border style="width: 100%">
        <el-table-column prop="event_no" label="事件编号" width="150" />
        <el-table-column prop="alarm_id" label="关联报警" width="100" align="center" />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="处置进度" min-width="200">
          <template #default="{ row }">
            <el-progress :percentage="progressPercentage(row)" :status="progressStatus(row)" :format="progressFormat" />
          </template>
        </el-table-column>
        <el-table-column prop="confirmed_by" label="确认人" width="110">
          <template #default="{ row }">{{ row.confirmed_by || '-' }}</template>
        </el-table-column>
        <el-table-column label="处置时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="完成时间" width="170">
          <template #default="{ row }">{{ row.resolved_at ? formatTime(row.resolved_at) : '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button
              v-permission="'emergency:export'"
              link
              type="success"
              :loading="exportingId === row.id"
              @click="exportReport(row)"
            >
              报告
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :page-sizes="[10, 20, 50, 100]"
        :total="pagination.total"
        layout="total, sizes, prev, pager, next, jumper"
        class="pagination"
        @size-change="handleSizeChange"
        @current-change="loadEvents"
      />
    </el-card>

    <!-- 事件详情 -->
    <el-drawer v-model="detailVisible" title="应急事件详情" size="800px">
      <div v-if="current" class="detail-content">
        <!-- 基础信息 -->
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="事件编号">{{ current.event_no }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTag(current.status)" size="small">{{ statusLabel(current.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="关联报警">{{ current.alarm_id }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(current.created_at) }}</el-descriptions-item>
        </el-descriptions>

        <!-- 时间轴 -->
        <div class="timeline-section">
          <h4>处置时间轴</h4>
          <TimelineEditor :event-id="current.id" :read-only="true" />
        </div>

        <!-- 操作按钮 -->
        <div class="action-section">
          <el-button type="info" v-permission="'emergency:export'" @click="exportReport(current)">
            导出报告
          </el-button>
          <el-button @click="detailVisible = false">关闭</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getOrganizationTree } from '@/api/organization'
import { getEmergencyEvents, exportEventReport } from '@/api/emergency'
import { stripEmptyChildren } from '@/utils/device'
import TimelineEditor from '@/components/TimelineEditor.vue'

const cascaderProps = {
  label: 'org_name',
  value: 'id',
  children: 'children',
  checkStrictly: true,
  emitPath: false,
}

const STATUS_OPTIONS = [
  { label: '处理中', value: 'processing' },
  { label: '已解决', value: 'resolved' },
  { label: '已关闭', value: 'closed' },
]

const loading = ref(false)
const exportingId = ref(null)
const rows = ref([])
const orgOptions = ref([])
const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const filters = reactive({
  event_no: null,
  status: null,
  org_id: null,
  range: null,
})

const detailVisible = ref(false)
const current = ref(null)

async function loadEvents() {
  loading.value = true
  try {
    const res = await getEmergencyEvents(buildParams())
    const data = res.data || {}
    rows.value = data.items || []
    pagination.total = data.total || 0
  } catch (err) {
    ElMessage.error(err.message || '加载应急事件列表失败')
  } finally {
    loading.value = false
  }
}

async function loadOrgTree() {
  try {
    const res = await getOrganizationTree()
    orgOptions.value = stripEmptyChildren(res.data || [])
  } catch (err) {
    // 组织架构加载失败不阻断列表展示
    console.warn('加载组织架构失败:', err)
  }
}

function buildParams() {
  const [start, end] = filters.range || []
  return {
    page: pagination.page,
    page_size: pagination.page_size,
    event_no: filters.event_no || undefined,
    status: filters.status || undefined,
    org_id: filters.org_id || undefined,
    start: start || undefined,
    end: end || undefined,
  }
}

function handleSearch() {
  pagination.page = 1
  loadEvents()
}

function handleReset() {
  filters.event_no = null
  filters.status = null
  filters.org_id = null
  filters.range = null
  handleSearch()
}

function handleSizeChange(size) {
  pagination.page_size = size
  pagination.page = 1
  loadEvents()
}

function openDetail(row) {
  current.value = row
  detailVisible.value = true
}

function progressPercentage(row) {
  if (row.status === 'resolved' || row.status === 'closed') return 100
  return 50
}

function progressStatus(row) {
  if (row.status === 'resolved' || row.status === 'closed') return 'success'
  return 'active'
}

function progressFormat(val) {
  if (val === 100) return '已完成'
  return `${val}%`
}

function statusTag(status) {
  const map = { processing: 'warning', resolved: 'success', closed: 'info' }
  return map[status] || 'default'
}

function statusLabel(status) {
  const map = { processing: '处理中', resolved: '已解决', closed: '已关闭' }
  return map[status] || status
}

function formatTime(dateStr) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** 导出报告：后端返回 HTML Blob，前端触发下载（FR-030） */
async function exportReport(event) {
  exportingId.value = event.id
  try {
    const blob = await exportEventReport(event.id)
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `应急事件报告_${event.event_no}.html`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('报告导出成功')
  } catch (err) {
    ElMessage.error(err.message || '导出报告失败')
  } finally {
    exportingId.value = null
  }
}

onMounted(() => {
  loadEvents()
  loadOrgTree()
})
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

.detail-content {
  .timeline-section {
    margin: 24px 0;
    padding: 16px;
    background-color: #f5f7fa;
    border-radius: 4px;

    h4 {
      margin: 0 0 16px 0;
      font-size: 16px;
      color: #303133;
    }
  }

  .action-section {
    margin-top: 24px;
    text-align: right;
  }
}
</style>
