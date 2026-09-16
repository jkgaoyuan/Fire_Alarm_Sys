<!--
联动日志 (Logs.vue)
3.4-B5

后端三个端点（列表 / 详情 / 导出）早已就绪，`api/linkage.js` 里也早就封装好了
`getLinkageLogs` / `getLogDetail` / `exportLinkageLogs`，但**前端一直没有页面
消费它们** —— 联动日志功能从未对用户可见。本页把它接上。

「演练」标记是本页的重点：模拟测试产生的日志与真实火警产生的日志，
不看标记的话长得一模一样。日志表本身没有 is_drill，由后端从关联告警带出。

权限码：linkage:view
-->
<template>
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="filter-card" shadow="never">
      <el-form :model="filters" inline>
        <el-form-item label="状态">
          <el-select
            v-model="filters.status"
            placeholder="全部状态"
            clearable
            style="width: 140px"
          >
            <el-option label="待执行" value="pending" />
            <el-option label="已下发" value="sent" />
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item label="预案 ID">
          <el-input
            v-model="filters.plan_id"
            placeholder="预案 ID"
            clearable
            style="width: 140px"
          />
        </el-form-item>
        <el-form-item label="告警 ID">
          <el-input
            v-model="filters.alarm_id"
            placeholder="告警 ID"
            clearable
            style="width: 140px"
          />
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 340px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
          <el-button @click="handleExport">导出</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 日志列表 -->
    <el-card class="table-card" shadow="never">
      <el-table :data="logs" v-loading="loading" border stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="预案" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.plan_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="动作" width="120">
          <template #default="{ row }">{{ actionLabel(row.action_type) }}</template>
        </el-table-column>
        <el-table-column label="目标设备" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.target_device_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="logStatusTagType(row.status)" size="small">
              {{ logStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="演练/模拟" width="110" align="center">
          <template #default="{ row }">
            <!-- 演练告警（模拟测试产生）与真实火警产生的日志必须能一眼分辨 -->
            <el-tag v-if="row.is_drill" size="small" type="info">演练</el-tag>
            <el-tag v-else-if="row.is_simulation" size="small" type="info" effect="plain">
              模拟
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="结果说明" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.result_message || '-' }}</template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="loadLogs"
        @current-change="loadLogs"
        style="margin-top: 16px; justify-content: flex-end"
      />
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { exportLinkageLogs, getLinkageLogs } from '@/api/linkage'
import { actionLabel, logStatusLabel, logStatusTagType } from './constants'

const logs = ref([])
const loading = ref(false)
const dateRange = ref(null)

const filters = reactive({
  status: null,
  plan_id: null,
  alarm_id: null,
})

const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0,
})

function buildParams() {
  return {
    page: pagination.page,
    page_size: pagination.page_size,
    status: filters.status || undefined,
    // 后端是 Optional[int]，空串会 422，所以空值一律不带
    plan_id: filters.plan_id || undefined,
    alarm_id: filters.alarm_id || undefined,
    start_time: dateRange.value?.[0] || undefined,
    end_time: dateRange.value?.[1] || undefined,
  }
}

async function loadLogs() {
  loading.value = true
  try {
    const res = await getLinkageLogs(buildParams())
    // 统一响应信封 {code, message, data}。后端拦截器对裸返回也放行，
    // 所以必须显式判 code，否则读 res.data.items 拿到 undefined 会被
    // `|| []` 兜底成空表——页面显示 0 条而一切"正常"。
    if (res.code === 200 && res.data) {
      logs.value = res.data.items || []
      pagination.total = res.data.total || 0
    } else {
      ElMessage.error(res.message || '获取联动日志失败')
    }
  } catch (error) {
    console.error('加载联动日志失败:', error)
    ElMessage.error('获取联动日志失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadLogs()
}

function resetFilters() {
  filters.status = null
  filters.plan_id = null
  filters.alarm_id = null
  dateRange.value = null
  pagination.page = 1
  loadLogs()
}

async function handleExport() {
  try {
    const blob = await exportLinkageLogs(buildParams())
    // 后端超过 1 万行时返回的是 JSON 信封而不是 CSV；带着 blob 去下载
    // 会得到一个打不开的文件，所以先探一次类型。
    if (blob?.type?.includes('application/json')) {
      const payload = JSON.parse(await blob.text())
      ElMessage.error(payload.message || '导出失败')
      return
    }
    const url = window.URL.createObjectURL(new Blob([blob]))
    const link = document.createElement('a')
    link.href = url
    link.download = `联动日志_${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    window.URL.revokeObjectURL(url)
  } catch (error) {
    console.error('导出联动日志失败:', error)
    ElMessage.error('导出失败')
  }
}

function formatTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
}

onMounted(loadLogs)
</script>

<style scoped>
.page-container {
  padding: 20px;
}

.filter-card,
.table-card {
  margin-bottom: 20px;
}
</style>
