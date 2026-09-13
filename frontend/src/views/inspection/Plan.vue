<!--
巡检计划管理页面 (3.6-F1)
PRD: 3.6 FR-032
功能：
- 巡检计划列表查询（分页 + 筛选）
- 创建/编辑/删除计划
- 启用/停用计划
- 手动生成任务
权限码：inspection:view/create/update/delete
-->
<template>
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="search-card" shadow="never">
      <el-form :model="searchForm" inline>
        <el-form-item label="区域">
          <el-cascader
            v-model="searchForm.org_id"
            :options="orgOptions"
            :props="cascaderProps"
            placeholder="全部区域"
            clearable
            style="width: 240px"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="searchForm.is_enabled"
            placeholder="全部状态"
            clearable
            style="width: 160px"
          >
            <el-option label="启用中" :value="true" />
            <el-option label="已停用" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 计划列表 -->
    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>巡检计划（共 {{ pagination.total }} 个）</span>
          <div>
            <PermissionButton
              permission="inspection:create"
              type="primary"
              @click="handleAdd"
            >
              <el-icon><plus /></el-icon>
              新增计划
            </PermissionButton>
          </div>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="planList"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="plan_name" label="计划名称" min-width="180" />
        <el-table-column prop="org_name" label="所属区域" width="160" show-overflow-tooltip />
        <el-table-column prop="device_type_name" label="设备类型" width="120" />
        <el-table-column prop="cycle_type" label="周期类型" width="100">
          <template #default="{ row }">
            <el-tag :type="cycleTypeTag(row.cycle_type)" size="small">
              {{ cycleTypeLabel(row.cycle_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="responsible_user_name" label="责任人" width="120" />
        <el-table-column label="时间范围" width="240">
          <template #default="{ row }">
            {{ formatDate(row.start_date) }} ~ {{ formatDate(row.end_date || '长期') }}
          </template>
        </el-table-column>
        <el-table-column label="统计信息" width="200">
          <template #default="{ row }">
            <div class="stats-info">
              <span>总任务：{{ row.total_tasks || 0 }}</span>
              <span>已完成：{{ row.completed_tasks || 0 }}</span>
              <span>漏检：{{ row.missed_tasks || 0 }}</span>
              <el-progress
                :percentage="Number((row.completion_rate * 100).toFixed(1))"
                :color="getProgressColor(row.completion_rate)"
                :format="() => `完成率 ${(row.completion_rate * 100).toFixed(1)}%`"
                style="margin-top: 4px"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="is_enabled" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">
              {{ row.is_enabled ? '启用中' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" align="center" fixed="right">
          <template #default="{ row }">
            <PermissionButton
              permission="inspection:view"
              link
              type="primary"
              @click="handleViewDetails(row)"
            >
              查看详情
            </PermissionButton>
            <PermissionButton
              permission="inspection:update"
              link
              type="primary"
              @click="handleEdit(row)"
            >
              编辑
            </PermissionButton>
            <PermissionButton
              permission="inspection:create"
              link
              type="success"
              @click="handleGenerateTasks(row)"
            >
              生成任务
            </PermissionButton>
            <PermissionButton
              permission="inspection:update"
              link
              :type="row.is_enabled ? 'warning' : 'primary'"
              @click="handleToggle(row)"
            >
              {{ row.is_enabled ? '停用' : '启用' }}
            </PermissionButton>
            <PermissionButton
              permission="inspection:delete"
              link
              type="danger"
              @click="handleDelete(row)"
            >
              删除
            </PermissionButton>
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
        @current-change="handlePageChange"
      />
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <PlanForm
      v-model="formVisible"
      :plan="currentPlan"
      :org-options="orgOptions"
      :device-types="deviceTypes"
      @success="loadPlans"
    />

    <!-- 详情弹窗 -->
    <PlanDetail
      v-model="detailVisible"
      :plan-id="detailPlanId"
      :org-options="orgOptions"
      @success="loadPlans"
    />
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PermissionButton from '@/components/PermissionButton.vue'
import PlanForm from './PlanForm.vue'
import PlanDetail from './PlanDetail.vue'
import { getOrganizationTree } from '@/api/organization'
import { getDeviceTypes } from '@/api/device'
import { getInspectionPlans } from '@/api/inspection'

const cascaderProps = {
  label: 'org_name',
  value: 'id',
  children: 'children',
  checkStrictly: true,
  emitPath: false,
}

const loading = ref(false)
const planList = ref([])
const orgOptions = ref([])
const deviceTypes = ref([])

const searchForm = reactive({
  org_id: null,
  is_enabled: null,
})

const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const formVisible = ref(false)
const detailVisible = ref(false)
const currentPlan = ref(null)
const detailPlanId = ref(null)

onMounted(() => {
  loadPlans()
  loadOrgTree()
  loadDeviceTypes()
})

// ==================== 数据加载 ====================

async function loadPlans() {
  loading.value = true
  try {
    const res = await getInspectionPlans({
      page: pagination.page,
      page_size: pagination.page_size,
      org_id: searchForm.org_id || undefined,
      is_enabled: searchForm.is_enabled || undefined,
    })
    const data = res.data || {}
    planList.value = data.items || []
    pagination.total = data.total || 0
  } catch (err) {
    ElMessage.error(err.message || '加载计划列表失败')
  } finally {
    loading.value = false
  }
}

async function loadOrgTree() {
  try {
    const res = await getOrganizationTree()
    orgOptions.value = res.data || []
  } catch (err) {
    ElMessage.error(err.message || '加载组织架构失败')
  }
}

async function loadDeviceTypes() {
  try {
    const res = await getDeviceTypes()
    deviceTypes.value = res.data || []
  } catch (err) {
    ElMessage.error(err.message || '加载设备类型失败')
  }
}

// ==================== 筛选与分页 ====================

function handleSearch() {
  pagination.page = 1
  loadPlans()
}

function handleReset() {
  searchForm.org_id = null
  searchForm.is_enabled = null
  handleSearch()
}

function handleSizeChange(size) {
  pagination.page_size = size
  pagination.page = 1
  loadPlans()
}

function handlePageChange(page) {
  pagination.page = page
  loadPlans()
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

function cycleTypeTag(type) {
  const map = {
    daily: undefined,
    weekly: 'warning',
    monthly: undefined,
    quarterly: undefined,
    yearly: 'success',
  }
  return map[type]
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  return dateStr.toString().slice(0, 10)
}

function getProgressColor(rate) {
  if (rate >= 0.8) return '#67C23A'
  if (rate >= 0.5) return '#E6A23C'
  return '#F56C6C'
}

// ==================== 操作 ====================

function handleAdd() {
  currentPlan.value = null
  formVisible.value = true
}

function handleEdit(row) {
  currentPlan.value = row
  formVisible.value = true
}

function handleViewDetails(row) {
  detailPlanId.value = row.id
  detailVisible.value = true
}

async function handleGenerateTasks(row) {
  try {
    const days = 7
    const response = await window.$axios({
      method: 'post',
      url: `/api/v1/inspection-plans/${row.id}/generate`,
      params: { days },
    })
    
    if (response.code === 200) {
      ElMessage.success(`已生成 ${days} 天的巡检任务`)
      loadPlans()
    } else {
      ElMessage.error(response.message || '生成任务失败')
    }
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || err.message || '生成任务失败')
  }
}

async function handleToggle(row) {
  try {
    const newStatus = !row.is_enabled
    const response = await window.$axios({
      method: 'post',
      url: `/api/v1/inspection-plans/${row.id}/toggle`,
      data: { is_enabled: newStatus },
    })
    
    if (response.code === 200) {
      ElMessage.success(newStatus ? '已启用' : '已停用')
      loadPlans()
    } else {
      ElMessage.error(response.message || '状态更新失败')
    }
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || err.message || '状态更新失败')
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除巡检计划「${row.plan_name}」吗？删除后不可恢复。`,
      '二次确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }
    )
    
    const response = await window.$axios({
      method: 'delete',
      url: `/api/v1/inspection-plans/${row.id}`,
    })
    
    if (response.code === 200 || response.code === 204 || response.status === 204) {
      ElMessage.success('删除成功')
      loadPlans()
    } else {
      ElMessage.error(response.message || '删除失败')
    }
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      ElMessage.error(err.response?.data?.detail || err.message || '删除失败')
    }
  }
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

  .stats-info {
    font-size: 13px;
    line-height: 1.8;
  }
}
</style>
