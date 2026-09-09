<template>
  <div class="page-container">
    <!-- 搜索栏 -->
    <el-card class="search-card" shadow="never">
      <el-form :model="searchForm" inline>
        <el-form-item label="用户名">
          <el-input
            v-model="searchForm.username"
            placeholder="请输入用户名"
            clearable
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="登录状态">
          <el-select
            v-model="searchForm.status"
            placeholder="全部状态"
            clearable
            style="width: 140px"
          >
            <el-option label="成功" value="success" />
            <el-option label="失败" value="fail" />
            <el-option label="锁定" value="locked" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="searchForm.timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DD HH:mm:ss"
            clearable
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 日志列表 -->
    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>登录日志</span>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="logList"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" width="120" />
        <el-table-column prop="login_type" label="登录方式" width="100">
          <template #default="{ row }">
            {{ loginTypeLabel(row.login_type) }}
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP 地址" width="140" />
        <el-table-column label="终端信息" min-width="200">
          <template #default="{ row }">
            <span v-if="row.device_type || row.device_os || row.browser">
              {{ [row.device_type, row.device_os, row.browser].filter(Boolean).join(' / ') }}
            </span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="fail_reason" label="失败原因" min-width="140">
          <template #default="{ row }">
            <span v-if="row.fail_reason" class="text-danger">{{ row.fail_reason }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="登录时间" width="180" />
      </el-table>

      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :page-sizes="[10, 20, 50, 100]"
        :total="pagination.total"
        layout="total, sizes, prev, pager, next, jumper"
        class="pagination"
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getLoginLogs } from '@/api/loginLog'

// ==================== 数据状态 ====================
const loading = ref(false)
const logList = ref([])
const searchForm = reactive({
  username: '',
  status: '',
  timeRange: [],
})
const pagination = reactive({
  page: 1,
  page_size: 10,
  total: 0,
})

// ==================== 生命周期 ====================
onMounted(() => {
  loadLogs()
})

// ==================== 数据加载 ====================
async function loadLogs() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.page_size,
      username: searchForm.username || undefined,
      status: searchForm.status || undefined,
    }
    if (searchForm.timeRange && searchForm.timeRange.length === 2) {
      params.start_time = searchForm.timeRange[0]
      params.end_time = searchForm.timeRange[1]
    }

    const res = await getLoginLogs(params)
    const data = res.data || {}
    logList.value = data.items || []
    pagination.total = data.total || 0
  } catch (err) {
    ElMessage.error(err.message || '加载登录日志失败')
  } finally {
    loading.value = false
  }
}

// ==================== 搜索与分页 ====================
function handleSearch() {
  pagination.page = 1
  loadLogs()
}

function handleReset() {
  searchForm.username = ''
  searchForm.status = ''
  searchForm.timeRange = []
  pagination.page = 1
  loadLogs()
}

function handleSizeChange() {
  pagination.page = 1
  loadLogs()
}

function handlePageChange() {
  loadLogs()
}

// ==================== 格式化 ====================
function statusType(status) {
  switch (status) {
    case 'success':
      return 'success'
    case 'locked':
      return 'danger'
    case 'fail':
      return 'warning'
    default:
      return 'info'
  }
}

function statusLabel(status) {
  switch (status) {
    case 'success':
      return '成功'
    case 'locked':
      return '锁定'
    case 'fail':
      return '失败'
    default:
      return status || '-'
  }
}

function loginTypeLabel(loginType) {
  switch (loginType) {
    case 'password':
      return '密码登录'
    default:
      return loginType || '-'
  }
}
</script>

<style scoped>
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

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.text-muted {
  color: #909399;
}

.text-danger {
  color: #f56c6c;
}
</style>
