<!--
消防演练管理页面 (3.8-F1)
PRD: 3.8 FR-043~FR-047
功能：
- 演练计划列表查询（分页 + 筛选）
- 创建/编辑/删除演练计划
- 执行演练（开始/完成/取消）
- 查看评估结果和导出报告
权限码：drill:view/create/update/delete/execute/evaluate
-->
<template>
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="search-card" shadow="never">
      <el-form :model="searchForm" inline>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部状态" clearable style="width: 120px">
            <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="searchForm.drill_type" placeholder="全部类型" clearable style="width: 120px">
            <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 演练列表 -->
    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>演练计划（共 {{ pagination.total }} 个）</span>
          <div>
            <PermissionButton permission="drill:create" type="primary" @click="handleAdd">
              <el-icon><Plus /></el-icon>
              新增演练
            </PermissionButton>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="drillList" stripe border style="width: 100%">
        <el-table-column prop="drill_name" label="演练名称" min-width="200" />
        <el-table-column prop="drill_type" label="演练类型" width="120">
          <template #default="{ row }">
            <el-tag :type="getTypeTag(row.drill_type)" size="small">{{ getTypeLabel(row.drill_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusTag(row.status)" size="small">{{ getStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="location" label="地点" width="150" show-overflow-tooltip />
        <el-table-column prop="planned_at" label="计划时间" width="180">
          <template #default="{ row }">{{ formatDate(row.planned_at) }}</template>
        </el-table-column>
        <el-table-column prop="participant_count" label="参与人数" width="80" />
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetailDialog(row.id)">详情</el-button>
            <PermissionButton
              v-if="canEdit(row)" link type="primary" permission="drill:update"
              @click="openPlanForm('edit', row.id)">编辑</PermissionButton>
            <PermissionButton
              v-if="canExecute(row)" link type="success" permission="drill:execute"
              @click="startExecute(row.id)">开始执行</PermissionButton>
            <PermissionButton
              v-if="canEvaluate(row)" link type="warning" permission="drill:evaluate"
              @click="openEvaluationDialog(row.id)">评估</PermissionButton>
            <PermissionButton link type="info" permission="drill:export" @click="exportReport(row.id)">导出报告</PermissionButton>
            <PermissionButton
              v-if="canDelete(row)" link type="danger" permission="drill:delete"
              @click="deleteDrill(row.id)">删除</PermissionButton>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchData"
          @current-change="fetchData"
        />
      </div>
    </el-card>

    <!-- PlanFormDialog -->
    <PlanFormDialog v-model="dialogVisible" :plan-data="selectedPlan" @submitted="onFormSubmitted" />

    <!-- DetailDialog -->
    <DetailDialog v-model="detailDialogVisible" :drill-id="selectedDrillId" @completed="fetchData" />

    <!-- EvaluationDialog -->
    <EvaluationDialog v-model="evalDialogVisible" :drill-id="selectedDrillId" @submitted="onEvalSubmitted" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PermissionButton from '@/components/PermissionButton.vue'
import PlanFormDialog from './PlanFormDialog.vue'
import DetailDialog from './DetailDialog.vue'
import EvaluationDialog from './EvaluationDialog.vue'
import { getDrills, deleteDrill as apiDeleteDrill, executeDrill, completeDrill, cancelDrill, getDrillDetail, getDrillReportHtml } from '@/api/drill'

// ==================== 数据状态 ====================

const loading = ref(false)
const drillList = ref([])
const dialogVisible = ref(false)
const selectedPlan = ref(null)
const searchMode = ref('add')

const detailDialogVisible = ref(false)
const evalDialogVisible = ref(false)
const selectedDrillId = ref(null)

const searchForm = reactive({
  status: undefined,
  drill_type: undefined,
})

const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0,
})

// ==================== 选项数据 ====================

const statusOptions = [
  { label: '计划中', value: 'planned' },
  { label: '执行中', value: 'ongoing' },
  { label: '已完成', value: 'completed' },
  { label: '已取消', value: 'cancelled' },
]

const typeOptions = [
  { label: '疏散演练', value: 'evacuation' },
  { label: '灭火演练', value: 'firefighting' },
  { label: '综合演练', value: 'comprehensive' },
]

// ==================== 辅助函数 ====================

function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const minute = String(d.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hour}:${minute}`
}

function getTypeLabel(type) {
  const map = { evacuation: '疏散演练', firefighting: '灭火演练', comprehensive: '综合演练' }
  return map[type] || type
}

function getStatusLabel(status) {
  const map = { planned: '计划中', ongoing: '执行中', completed: '已完成', cancelled: '已取消' }
  return map[status] || status
}

function getTypeTag(type) {
  const map = { evacuation: 'primary', firefighting: 'success', comprehensive: 'warning' }
  return map[type] || 'info'
}

function getStatusTag(status) {
  const map = { planned: 'info', ongoing: 'warning', completed: 'success', cancelled: 'danger' }
  return map[status] || 'info'
}

function canEdit(row) { return ['planned'].includes(row.status) }
function canExecute(row) { return ['planned'].includes(row.status) }
function canEvaluate(row) { return ['completed'].includes(row.status) }
function canDelete(row) { return ['planned', 'cancelled'].includes(row.status) }

// ==================== CRUD 操作 ====================

async function fetchData() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      status_filter: searchForm.status || undefined,
      drill_type: searchForm.drill_type || undefined,
    }

    const res = await getDrills(params)
    const data = res.data || {}

    drillList.value = data.items || []
    pagination.total = data.total || 0
  } catch (err) {
    console.error(err)
    ElMessage.error('获取演练列表失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  fetchData()
}

function handleReset() {
  Object.assign(searchForm, { status: undefined, drill_type: undefined })
  handleSearch()
}

function handleAdd() {
  searchMode.value = 'add'
  selectedPlan.value = null
  dialogVisible.value = true
}

function openPlanForm(mode, id) {
  searchMode.value = mode
  if (mode === 'edit') {
    selectedPlan.value = { id }
  } else {
    selectedPlan.value = null
  }
  dialogVisible.value = true
}

function openDetailDialog(id) {
  selectedDrillId.value = id
  detailDialogVisible.value = true
}

function startExecute(id) {
  ElMessageBox.confirm('确认开始执行该演练吗？已记录现场照片与视频。', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(async () => {
    try {
      await executeDrill(id, {})
      ElMessage.success('演练已开始执行')
      fetchData()
    } catch (err) {
      ElMessage.error(err.message || '执行失败')
    }
  }).catch(() => {})
}

function closeDetailDialog() {
  detailDialogVisible.value = false
  setTimeout(() => { selectedDrillId.value = null }, 300)
}

function completeDrillAction(id, summary) {
  ElMessageBox.prompt('请填写演练总结（含现场情况、成效等）', '完成演练', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '请描述演练情况...',
    inputValue: summary || '',
  }).then(async ({ value }) => {
    try {
      await completeDrill(id, { summary: value })
      ElMessage.success('演练已完成')
      fetchData()
      closeDetailDialog()
    } catch (err) {
      ElMessage.error(err.message || '完成失败')
    }
  }).catch(() => {})
}

function cancelDrillAction(id, reason) {
  ElMessageBox.prompt('请输入取消原因', '取消演练', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '取消原因',
  }).then(async ({ value }) => {
    try {
      await cancelDrill(id, { reason: value })
      ElMessage.success('演练已取消')
      fetchData()
      closeDetailDialog()
    } catch (err) {
      ElMessage.error(err.message || '取消失败')
    }
  }).catch(() => {})
}

function openEvaluationDialog(id) {
  selectedDrillId.value = id
  evalDialogVisible.value = true
}

function onEvalSubmitted() {
  evalDialogVisible.value = false
  fetchData()
  ElMessage.success('评估提交成功')
}

async function exportReport(drillId) {
  try {
    const res = await getDrillReportHtml(drillId)
    const html = res.data || ''
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `消防演练报告_${Date.now()}.html`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('报告导出成功')
  } catch (err) {
    console.error(err)
    ElMessage.error('导出报告失败')
  }
}

async function deleteDrill(id) {
  ElMessageBox.confirm('确认删除该演练计划？此操作不可恢复且会级联删除评估数据。', '警告', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'error',
  }).then(async () => {
    try {
      await apiDeleteDrill(id)
      ElMessage.success('删除成功')
      fetchData()
    } catch (err) {
      ElMessage.error(err.message || '删除失败')
    }
  }).catch(() => {})
}

function onFormSubmitted() {
  dialogVisible.value = false
  fetchData()
  ElMessage.success('保存成功')
}

// ==================== 生命周期 ====================

onMounted(() => {
  fetchData()
})
</script>

<style scoped lang="scss">
.page-container { padding: 20px }
.search-card { margin-bottom: 20px }
.table-card { margin-bottom: 20px }
.card-header { display: flex; justify-content: space-between; align-items: center }
.pagination-container { display: flex; justify-content: flex-end; margin-top: 20px }
</style>
