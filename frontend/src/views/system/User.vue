<template>
  <div class="page-container">
    <!-- 搜索栏 -->
    <el-card class="search-card" shadow="never">
      <el-form :model="searchForm" inline>
        <el-form-item label="关键字">
          <el-input
            v-model="searchForm.keyword"
            placeholder="用户名 / 真实姓名 / 手机号"
            clearable
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 用户列表 -->
    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>用户列表</span>
          <PermissionButton
            permission="system:user:create"
            type="primary"
            @click="handleAdd"
          >
            <el-icon><plus /></el-icon>
            新增用户
          </PermissionButton>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="userList"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="username" label="用户名" width="120" />
        <el-table-column prop="real_name" label="真实姓名" width="120" />
        <el-table-column prop="phone" label="手机号" width="130" />
        <el-table-column prop="org_name" label="所属部门" width="150" />
        <el-table-column label="角色" min-width="180">
          <template #default="{ row }">
            <el-tag
              v-for="role in row.roles"
              :key="role.role_code"
              size="small"
              class="role-tag"
            >
              {{ role.role_name }}
            </el-tag>
            <span v-if="!row.roles || row.roles.length === 0" class="text-muted">未分配</span>
          </template>
        </el-table-column>
        <el-table-column prop="data_scope" label="数据范围" width="160">
          <template #default="{ row }">
            <el-tag :type="dataScopeType(row.data_scope)" size="small">
              {{ dataScopeLabel(row.data_scope) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-permission="'system:user:update'"
              link
              type="primary"
              @click="handleEdit(row)"
            >
              编辑
            </el-button>

            <!-- 锁定中用户显示解锁 -->
            <el-button
              v-if="row.status === 'locked'"
              v-permission="'system:user:update'"
              link
              type="success"
              @click="handleUnlock(row)"
            >
              解锁
            </el-button>
            <!-- 正常用户可禁用 -->
            <el-button
              v-else-if="row.status === 'active'"
              v-permission="'system:user:update'"
              link
              type="warning"
              @click="handleDisable(row)"
            >
              禁用
            </el-button>
            <!-- 已禁用用户可启用 -->
            <el-button
              v-else-if="row.status === 'disabled'"
              v-permission="'system:user:update'"
              link
              type="primary"
              @click="handleEnable(row)"
            >
              启用
            </el-button>

            <el-button
              v-permission="'system:user:resetpwd'"
              link
              type="primary"
              @click="handleResetPassword(row)"
            >
              重置密码
            </el-button>

            <el-button
              v-permission="'system:user:update'"
              link
              type="primary"
              @click="handleAssignRoles(row)"
            >
              分配角色
            </el-button>

            <el-button
              v-permission="'system:user:delete'"
              link
              type="danger"
              @click="handleDelete(row)"
            >
              删除
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
        @current-change="handlePageChange"
      />
    </el-card>

    <!-- 新增 / 编辑用户弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="560px"
      destroy-on-close
      :close-on-click-modal="false"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="100px"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :disabled="isEdit"
          />
        </el-form-item>
        <el-form-item
          v-if="!isEdit"
          label="初始密码"
          prop="password"
        >
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="请输入初始密码（至少 8 位，含字母和数字）"
          />
        </el-form-item>
        <el-form-item label="真实姓名" prop="real_name">
          <el-input v-model="form.real_name" placeholder="请输入真实姓名" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="form.phone" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="数据范围" prop="data_scope">
          <el-select v-model="form.data_scope" placeholder="请选择数据范围" style="width: 100%">
            <el-option label="全部" value="all" />
            <el-option label="本部门及子部门" value="dept" />
            <el-option label="仅本人" value="self" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色" prop="role_ids">
          <el-select
            v-model="form.role_ids"
            multiple
            placeholder="请选择角色"
            style="width: 100%"
          >
            <el-option
              v-for="role in allRoles"
              :key="role.id"
              :label="role.role_name"
              :value="role.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="form.status">
            <el-radio label="active">正常</el-radio>
            <el-radio label="disabled">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 重置密码弹窗 -->
    <el-dialog
      v-model="resetPwdVisible"
      title="重置密码"
      width="420px"
      destroy-on-close
    >
      <div v-if="!resetPwdResult">
        <p>确定为用户 <strong>{{ currentUser?.real_name || currentUser?.username }}</strong> 重置密码吗？</p>
        <p class="tip-text">重置后将生成随机密码并显示在弹窗中，请妥善保管。</p>
      </div>
      <div v-else>
        <p>用户 <strong>{{ currentUser?.real_name || currentUser?.username }}</strong> 的密码已重置：</p>
        <div class="password-box">
          <span class="password-text">{{ resetPwdResult }}</span>
          <el-button type="primary" link @click="copyPassword">
            复制
          </el-button>
        </div>
        <p class="tip-text">请尽快通知用户修改密码。</p>
      </div>
      <template #footer>
        <el-button v-if="!resetPwdResult" @click="resetPwdVisible = false">取消</el-button>
        <el-button
          v-if="!resetPwdResult"
          type="primary"
          :loading="resetPwdLoading"
          @click="confirmResetPassword"
        >
          确定重置
        </el-button>
        <el-button v-else type="primary" @click="resetPwdVisible = false">
          完成
        </el-button>
      </template>
    </el-dialog>

    <!-- 分配角色弹窗 -->
    <el-dialog
      v-model="assignRoleVisible"
      title="分配角色"
      width="450px"
      destroy-on-close
    >
      <el-checkbox-group v-model="selectedRoleIds">
        <el-checkbox
          v-for="role in allRoles"
          :key="role.id"
          :label="role.id"
          border
          class="role-checkbox"
        >
          {{ role.role_name }}
        </el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="assignRoleVisible = false">取消</el-button>
        <el-button type="primary" :loading="assignRoleLoading" @click="confirmAssignRoles">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  getUsers,
  createUser,
  updateUser,
  deleteUser,
  updateUserStatus,
  assignUserRoles,
  resetUserPassword,
  getAllRoles,
} from '@/api/user'

// ==================== 数据状态 ====================
const loading = ref(false)
const userList = ref([])
const allRoles = ref([])
const searchForm = reactive({
  keyword: '',
})
const pagination = reactive({
  page: 1,
  page_size: 10,
  total: 0,
})

// ==================== 新增 / 编辑弹窗 ====================
const dialogVisible = ref(false)
const dialogTitle = ref('新增用户')
const submitLoading = ref(false)
const formRef = ref(null)
const isEdit = ref(false)
const currentUserId = ref(null)

const form = reactive({
  username: '',
  password: '',
  real_name: '',
  phone: '',
  email: '',
  data_scope: 'self',
  role_ids: [],
  status: 'active',
})

const validatePassword = (rule, value, callback) => {
  if (!isEdit.value && !value) {
    callback(new Error('请输入初始密码'))
    return
  }
  if (value && value.length < 8) {
    callback(new Error('密码长度至少 8 位'))
    return
  }
  if (value && (!/[A-Za-z]/.test(value) || !/\d/.test(value))) {
    callback(new Error('密码必须同时包含字母和数字'))
    return
  }
  callback()
}

const formRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, validator: validatePassword, trigger: 'blur' },
  ],
  email: [
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  data_scope: [
    { required: true, message: '请选择数据范围', trigger: 'change' },
  ],
}

// ==================== 重置密码弹窗 ====================
const resetPwdVisible = ref(false)
const resetPwdLoading = ref(false)
const currentUser = ref(null)
const resetPwdResult = ref('')

// ==================== 分配角色弹窗 ====================
const assignRoleVisible = ref(false)
const assignRoleLoading = ref(false)
const selectedRoleIds = ref([])

// ==================== 生命周期 ====================
onMounted(() => {
  loadUsers()
  loadAllRoles()
})

// ==================== 数据加载 ====================
async function loadUsers() {
  loading.value = true
  try {
    const res = await getUsers({
      page: pagination.page,
      page_size: pagination.page_size,
      keyword: searchForm.keyword,
    })
    const data = res.data || {}
    userList.value = data.items || []
    pagination.total = data.total || 0
  } catch (err) {
    ElMessage.error(err.message || '加载用户列表失败')
  } finally {
    loading.value = false
  }
}

async function loadAllRoles() {
  try {
    const res = await getAllRoles()
    allRoles.value = res.data || []
  } catch (err) {
    ElMessage.error(err.message || '加载角色列表失败')
  }
}

// ==================== 搜索与分页 ====================
function handleSearch() {
  pagination.page = 1
  loadUsers()
}

function handleReset() {
  searchForm.keyword = ''
  pagination.page = 1
  loadUsers()
}

function handleSizeChange(size) {
  pagination.page_size = size
  pagination.page = 1
  loadUsers()
}

function handlePageChange(page) {
  pagination.page = page
  loadUsers()
}

// ==================== 状态标签工具函数 ====================
function statusType(status) {
  const map = {
    active: 'success',
    locked: 'danger',
    disabled: 'info',
  }
  return map[status] || 'info'
}

function statusLabel(status) {
  const map = {
    active: '正常',
    locked: '锁定中',
    disabled: '已禁用',
  }
  return map[status] || status
}

function dataScopeType(scope) {
  const map = {
    all: 'success',
    dept: 'warning',
    self: 'info',
  }
  return map[scope] || 'info'
}

function dataScopeLabel(scope) {
  const map = {
    all: '全部',
    dept: '本部门及子部门',
    self: '仅本人',
  }
  return map[scope] || scope
}

// ==================== 新增 / 编辑 ====================
function resetForm() {
  form.username = ''
  form.password = ''
  form.real_name = ''
  form.phone = ''
  form.email = ''
  form.data_scope = 'self'
  form.role_ids = []
  form.status = 'active'
  nextTick(() => {
    formRef.value?.resetFields()
  })
}

function handleAdd() {
  isEdit.value = false
  currentUserId.value = null
  dialogTitle.value = '新增用户'
  resetForm()
  dialogVisible.value = true
}

function handleEdit(row) {
  isEdit.value = true
  currentUserId.value = row.id
  dialogTitle.value = '编辑用户'
  resetForm()

  // 回填数据
  nextTick(() => {
    form.username = row.username
    form.real_name = row.real_name || ''
    form.phone = row.phone || ''
    form.email = row.email || ''
    form.data_scope = row.data_scope || 'self'
    form.role_ids = (row.roles || []).map((r) => r.id)
    form.status = row.status === 'locked' ? 'active' : row.status
  })

  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitLoading.value = true
  try {
    if (isEdit.value) {
      await updateUser(currentUserId.value, {
        real_name: form.real_name || undefined,
        phone: form.phone || undefined,
        email: form.email || undefined,
        data_scope: form.data_scope,
        role_ids: form.role_ids,
        status: form.status,
      })
      ElMessage.success('用户更新成功')
    } else {
      await createUser({
        username: form.username,
        password: form.password,
        real_name: form.real_name || undefined,
        phone: form.phone || undefined,
        email: form.email || undefined,
        data_scope: form.data_scope,
        role_ids: form.role_ids,
      })
      ElMessage.success('用户创建成功')
    }
    dialogVisible.value = false
    loadUsers()
  } catch (err) {
    ElMessage.error(err.message || '提交失败')
  } finally {
    submitLoading.value = false
  }
}

// ==================== 删除 ====================
async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户 "${row.real_name || row.username}" 吗？删除后不可恢复。`,
      '二次确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    await deleteUser(row.id)
    ElMessage.success('删除成功')
    loadUsers()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || '删除失败')
    }
  }
}

// ==================== 状态操作 ====================
async function handleUnlock(row) {
  try {
    await ElMessageBox.confirm(
      `确定解锁用户 "${row.real_name || row.username}" 吗？`,
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    await updateUserStatus(row.id, { status: 'active' })
    ElMessage.success('解锁成功')
    loadUsers()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || '解锁失败')
    }
  }
}

async function handleDisable(row) {
  try {
    await ElMessageBox.confirm(
      `确定禁用用户 "${row.real_name || row.username}" 吗？禁用后该用户将无法登录。`,
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    await updateUserStatus(row.id, { status: 'disabled' })
    ElMessage.success('禁用成功')
    loadUsers()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || '禁用失败')
    }
  }
}

async function handleEnable(row) {
  try {
    await ElMessageBox.confirm(
      `确定启用用户 "${row.real_name || row.username}" 吗？`,
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'info',
      }
    )
    await updateUserStatus(row.id, { status: 'active' })
    ElMessage.success('启用成功')
    loadUsers()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || '启用失败')
    }
  }
}

// ==================== 重置密码 ====================
function handleResetPassword(row) {
  currentUser.value = row
  resetPwdResult.value = ''
  resetPwdVisible.value = true
}

async function confirmResetPassword() {
  if (!currentUser.value) return
  resetPwdLoading.value = true
  try {
    const res = await resetUserPassword(currentUser.value.id)
    resetPwdResult.value = res.data?.new_password || ''
    ElMessage.success('密码重置成功')
    loadUsers()
  } catch (err) {
    ElMessage.error(err.message || '重置密码失败')
  } finally {
    resetPwdLoading.value = false
  }
}

function copyPassword() {
  if (!resetPwdResult.value) return
  navigator.clipboard.writeText(resetPwdResult.value).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.warning('复制失败，请手动复制')
  })
}

// ==================== 分配角色 ====================
function handleAssignRoles(row) {
  currentUser.value = row
  selectedRoleIds.value = (row.roles || []).map((r) => r.id)
  assignRoleVisible.value = true
}

async function confirmAssignRoles() {
  if (!currentUser.value) return
  assignRoleLoading.value = true
  try {
    await assignUserRoles(currentUser.value.id, {
      role_ids: selectedRoleIds.value,
    })
    ElMessage.success('角色分配成功')
    assignRoleVisible.value = false
    loadUsers()
  } catch (err) {
    ElMessage.error(err.message || '角色分配失败')
  } finally {
    assignRoleLoading.value = false
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

.role-tag {
  margin-right: 6px;
}

.role-checkbox {
  margin-bottom: 10px;
  margin-right: 10px;
}

.text-muted {
  color: #909399;
  font-size: 13px;
}

.tip-text {
  color: #909399;
  font-size: 13px;
  margin-top: 8px;
}

.password-box {
  margin-top: 12px;
  padding: 12px;
  background-color: #f5f7fa;
  border-radius: 4px;
  display: flex;
  justify-content: space-between;
  align-items: center;

  .password-text {
    font-family: monospace;
    font-size: 16px;
    font-weight: bold;
    color: #303133;
    word-break: break-all;
  }
}
</style>
