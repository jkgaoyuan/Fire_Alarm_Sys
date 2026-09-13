<!--
维修工单列表页 (OrderList.vue)
3.7-F1
功能：
- 工单列表查询（分页 + 筛选）
- 创建维修工单
- 状态流转操作（派单、完成、验收）
- 查看工单详情
-->
<template>
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="search-card" shadow="never">
      <el-form :model="filters" inline>
        <el-form-item label="状态">
          <el-select
            v-model="filters.status"
            placeholder="全部状态"
            clearable
            style="width: 160px"
          >
            <el-option label="待派单" value="pending" />
            <el-option label="已派单" value="assigned" />
            <el-option label="维修中" value="repairing" />
            <el-option label="待验收" value="pending_accept" />
            <el-option label="已完成" value="completed" />
            <el-option label="已退回" value="returned" />
          </el-select>
        </el-form-item>
        <el-form-item label="创建日期">
          <el-date-picker
            v-model="filters.date_range"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 280px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
          <el-button type="success" @click="handleCreate">创建工单</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 工单列表 -->
    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>维修工单（共 {{ pagination.total }} 条）</span>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="orderList"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="order_no" label="工单编号" width="180" show-overflow-tooltip />
        <el-table-column prop="device_name" label="设备名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="device_code" label="设备编码" width="140" show-overflow-tooltip />
        <el-table-column prop="fault_desc" label="故障描述" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="repairer_name" label="维修人员" width="120" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.repairer_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="reporter_name" label="报修人" width="120" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.reporter_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleView(row)">详情</el-button>
            <el-button
              v-if="row.status === 'pending'"
              v-permission="'repair:assign'"
              link
              type="warning"
              @click="handleAssign(row)"
            >
              派单
            </el-button>
            <el-button
              v-if="row.status === 'assigned'"
              v-permission="'repair:repair'"
              link
              type="success"
              @click="handleStartRepair(row)"
            >
              开始维修
            </el-button>
            <el-button
              v-if="row.status === 'repairing'"
              v-permission="'repair:repair'"
              link
              type="primary"
              @click="handleComplete(row)"
            >
              完成维修
            </el-button>
            <el-button
              v-if="row.status === 'pending_accept'"
              v-permission="'repair:accept'"
              link
              type="success"
              @click="handleAccept(row)"
            >
              验收通过
            </el-button>
            <el-button
              v-if="row.status === 'pending_accept'"
              v-permission="'repair:accept'"
              link
              type="danger"
              @click="handleReturn(row)"
            >
              验收退回
            </el-button>
            <el-button
              v-if="row.status === 'returned'"
              v-permission="'repair:repair'"
              link
              type="primary"
              @click="handleStartRepair(row)"
            >
              重新维修
            </el-button>
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

    <!-- 创建工单弹窗 -->
    <OrderForm
      v-model="formVisible"
      @success="loadOrders"
    />

    <!-- 工单详情弹窗 -->
    <OrderDetail
      v-model="detailVisible"
      :order="currentOrder"
      @success="loadOrders"
    />

    <!-- 派单弹窗 -->
    <el-dialog
      v-model="assignDialogVisible"
      title="派单"
      width="460px"
      destroy-on-close
      :close-on-click-modal="false"
    >
      <el-form
        ref="assignFormRef"
        :model="assignForm"
        :rules="assignRules"
        label-width="100px"
      >
        <el-form-item label="维修人员" prop="repairer_id">
          <el-select
            v-model="assignForm.repairer_id"
            placeholder="搜索并选择维修人员"
            filterable
            :loading="repairerLoading"
            style="width: 100%"
          >
            <el-option
              v-for="user in repairerOptions"
              :key="user.id"
              :label="`${user.real_name || user.username} (${user.username})`"
              :value="user.id"
            >
              <span>{{ user.real_name || user.username }}</span>
              <span style="float: right; color: #8492a6; font-size: 12px">
                {{ user.roles?.map((r) => r.role_name).join('、') || '' }}
              </span>
            </el-option>
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="assignLoading" @click="confirmAssign">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import OrderForm from './OrderForm.vue'
import OrderDetail from './OrderDetail.vue'
import { getRepairOrders, assignRepairOrder, startRepairOrder, completeRepairOrder, acceptRepairOrder, returnRepairOrder } from '@/api/repair'
import { getUsers } from '@/api/user'

// 操作列按钮一律用 v-permission 判**权限码**（repair:assign / repair:repair /
// repair:accept），与后端 require_permission 同口径。
// 此前「派单」判的是 `role_code === 'chief'`——前端判角色、后端判权限码，
// 两套口径：主管被撤销 repair:assign 后按钮照显示（点击才 403），
// 非 chief 角色被授予 repair:assign 后按钮反而被藏起来。

const loading = ref(false)
const orderList = ref([])

const filters = reactive({
  status: null,
  date_range: [],
})

const pagination = reactive({ page: 1, page_size: 20, total: 0 })

// Dialogs
const formVisible = ref(false)
const detailVisible = ref(false)
const currentOrder = ref(null)

// 派单弹窗
const assignDialogVisible = ref(false)
const assignLoading = ref(false)
const assignFormRef = ref(null)
const currentAssignOrder = ref(null)
const repairerOptions = ref([])
const repairerLoading = ref(false)

const assignForm = reactive({
  repairer_id: null,
})

const assignRules = {
  repairer_id: [{ required: true, message: '请选择维修人员', trigger: 'change' }],
}

onMounted(() => {
  loadOrders()
})

// ==================== 数据加载 ====================

async function loadOrders() {
  loading.value = true
  try {
    const [start, end] = filters.date_range || []
    
    const res = await getRepairOrders({
      page: pagination.page,
      page_size: pagination.page_size,
      status: filters.status || undefined,
      start_date: start || undefined,
      end_date: end || undefined,
    })

    // 后端已统一为响应信封 {code, message, data}（2026-09-13 迁移）
    const data = res.data || {}
    orderList.value = data.items || []
    pagination.total = data.total || 0
  } catch (err) {
    ElMessage.error(err.message || '加载工单列表失败')
  } finally {
    loading.value = false
  }
}

// ==================== 筛选与分页 ====================

function handleSearch() {
  pagination.page = 1
  loadOrders()
}

function handleReset() {
  filters.status = null
  filters.date_range = []
  handleSearch()
}

function handleSizeChange(size) {
  pagination.page_size = size
  pagination.page = 1
  loadOrders()
}

function handlePageChange(page) {
  pagination.page = page
  loadOrders()
}

// ==================== 辅助函数 ====================

function statusLabel(status) {
  const map = {
    pending: '待派单',
    assigned: '已派单',
    repairing: '维修中',
    pending_accept: '待验收',
    completed: '已完成',
    returned: '已退回',
  }
  return map[status] || status
}

function statusType(status) {
  const map = {
    pending: undefined,
    assigned: 'warning',
    repairing: 'warning',
    pending_accept: 'primary',
    completed: 'success',
    returned: 'danger',
  }
  return map[status] || undefined
}

// ==================== 操作 ====================

function handleCreate() {
  formVisible.value = true
}

function handleView(row) {
  currentOrder.value = row
  detailVisible.value = true
}

async function loadRepairerOptions() {
  repairerLoading.value = true
  try {
    // 只列**能真正接手**的人：后端按权限码过滤（不传则返回全量）。
    // 不过滤会留下死结——把工单派给没有 repair:repair 的人（如值班员），
    // 对方连「开始维修」都点不动，工单被派出去就卡住。
    const res = await getUsers({
      page: 1,
      page_size: 100,
      permission: 'repair:repair',
    })
    const data = res.data || {}
    const users = data.items || []
    // 只展示活跃用户，选项中标注角色便于识别
    repairerOptions.value = users.filter((u) => u.status === 'active')
  } catch (err) {
    ElMessage.error(err.message || '加载人员列表失败')
  } finally {
    repairerLoading.value = false
  }
}

function handleAssign(row) {
  currentAssignOrder.value = row
  assignForm.repairer_id = null
  assignDialogVisible.value = true
  loadRepairerOptions()
}

async function confirmAssign() {
  const valid = await assignFormRef.value?.validate().catch(() => false)
  if (!valid) return

  assignLoading.value = true
  try {
    await assignRepairOrder(currentAssignOrder.value.id, {
      repairer_id: assignForm.repairer_id,
    })
    ElMessage.success('派单成功')
    assignDialogVisible.value = false
    loadOrders()
  } catch (err) {
    ElMessage.error(err.message || '派单失败')
  } finally {
    assignLoading.value = false
  }
}

async function handleStartRepair(row) {
  // 同时服务两个入口：已派单工单的「开始维修」、已退回工单的「重新维修」。
  // 两者在状态机上都是 → repairing（REPAIR_ORDER_STATUS_TRANSITIONS）。
  const isReturned = row.status === 'returned'
  try {
    await ElMessageBox.confirm(
      isReturned ? '确认重新开始维修？' : '确认开始维修？',
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )

    const res = await startRepairOrder(row.id)
    if (res.code === 200) {
      ElMessage.success(isReturned ? '已重新开始维修' : '已开始维修')
      loadOrders()
    } else {
      ElMessage.error(res.message || '操作失败')
    }
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || '操作失败')
    }
  }
}

async function handleComplete(row) {
  try {
    const { value } = await ElMessageBox.prompt('请输入维修结果（含配件明细）', '完成维修', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputPlaceholder: '请详细描述维修结果和更换的配件',
    })
    
    await completeRepairOrder(row.id, { repair_result: value })
    ElMessage.success('维修完成，等待验收')
    loadOrders()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || '操作失败')
    }
  }
}

async function handleAccept(row) {
  try {
    await ElMessageBox.confirm('确认验收通过？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'success',
    })
    
    await acceptRepairOrder(row.id)
    ElMessage.success('验收通过')
    loadOrders()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || '验收失败')
    }
  }
}

async function handleReturn(row) {
  try {
    const { value } = await ElMessageBox.prompt('请输入退回原因', '验收退回', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputPlaceholder: '请说明退回原因',
    })
    
    await returnRepairOrder(row.id, { return_reason: value })
    ElMessage.success('已退回，等待重新维修')
    loadOrders()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || '操作失败')
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
}
</style>
