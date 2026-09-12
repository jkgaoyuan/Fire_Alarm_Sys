<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>巡检完成率</span>
          <div>
            <el-button size="small" @click="$router.back()">返回</el-button>
            <el-button size="small" type="primary" style="margin-left: 8px;" @click="handleExport">导出Excel</el-button>
          </div>
        </div>
      </template>

      <!-- 总体统计卡片 -->
      <el-row :gutter="20" class="summary-cards">
        <el-col :span="6">
          <el-statistic title="总任务数" :value="overall.total" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="已完成" :value="overall.completed" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="漏检" :value="overall.missed" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="完成率" :value="((overall.completion_rate || 0) * 100).toFixed(1) + '%'" />
        </el-col>
      </el-row>

      <!-- 责任人统计表格 -->
      <el-table :data="items" border stripe style="margin-top: 20px;">
        <el-table-column prop="responsible_name" label="责任人" />
        <el-table-column prop="total" label="总任务" />
        <el-table-column prop="completed" label="已完成" />
        <el-table-column prop="missed" label="漏检" />
        <el-table-column prop="pending" label="待执行" />
        <el-table-column label="完成率">
          <template #default="{ row }">
            <el-progress
              :percentage="(row.completion_rate * 100).toFixed(1)"
              :color="row.completion_rate >= 0.9 ? '#67c23a' : row.completion_rate >= 0.7 ? '#e6a23c' : '#f56c6c'"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getInspectionCompletion } from '@/api/statistics'
import { createExportTask } from '@/api/reports'

const items = ref([])
const overall = ref({})

async function loadData() {
  try {
    const res = await getInspectionCompletion()
    items.value = res.data.items || []
    overall.value = res.data.overall || {}
  } catch (err) {
    ElMessage.error(err.message || '加载数据失败')
  }
}

async function handleExport() {
  try {
    await createExportTask({
      task_type: 'inspection',
      params: {},
      data: items.value,
      format: 'xlsx',
    })
    ElMessage.success('导出任务已创建，请前往导出中心下载')
  } catch (err) {
    ElMessage.error(err.message || '导出失败')
  }
}

onMounted(() => {
  loadData()
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

.summary-cards {
  margin-bottom: 20px;
  padding: 20px;
  background: #f5f7fa;
  border-radius: 8px;
}
</style>
