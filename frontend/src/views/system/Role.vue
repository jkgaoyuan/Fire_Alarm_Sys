<template>
  <div class="page-container">
    <!-- 搜索栏 -->
    <el-card class="search-card" shadow="never">
      <el-form :model="searchForm" inline>
        <el-form-item label="角色名称">
          <el-input
            v-model="searchForm.keyword"
            placeholder="请输入角色名称"
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

    <!-- 操作栏 -->
    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>角色列表</span>
          <PermissionButton
            permission="system:role:create"
            type="primary"
            @click="handleAdd"
          >
            <el-icon><plus /></el-icon>
            新增角色
          </PermissionButton>
        </div>
      </template>

      <!-- 表格 -->
      <el-table
        v-loading="loading"
        :data="roleList"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="role_code" label="角色编码" width="150" />
        <el-table-column prop="role_name" label="角色名称" width="150" />
        <el-table-column prop="description" label="描述" show-overflow-tooltip />
        <el-table-column prop="is_builtin" label="是否内置" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_builtin" type="warning">内置</el-tag>
            <el-tag v-else type="info">自定义</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-permission="'system:role:update'"
              link
              type="primary"
              :disabled="row.is_builtin"
              @click="handleEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-permission="'system:role:delete'"
              link
              type="danger"
              :disabled="row.is_builtin"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
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

    <!-- 新增 / 编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="600px"
      destroy-on-close
      :close-on-click-modal="false"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="80px"
      >
        <el-form-item label="角色名称" prop="role_name">
          <el-input v-model="form.role_name" placeholder="请输入角色名称" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="请输入角色描述"
          />
        </el-form-item>
        <el-form-item label="权限配置" prop="perm_ids">
          <el-tree
            ref="treeRef"
            :data="permissionTree"
            show-checkbox
            node-key="id"
            :props="treeProps"
            check-strictly
            default-expand-all
            class="perm-tree"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
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
  getRoles,
  createRole,
  updateRole,
  deleteRole,
  getRolePermissions,
  getPermissionTree,
} from '@/api/role'

// ==================== 数据状态 ====================
const loading = ref(false)
const roleList = ref([])
const searchForm = reactive({
  keyword: '',
})
const pagination = reactive({
  page: 1,
  page_size: 10,
  total: 0,
})

// ==================== 弹窗与表单 ====================
const dialogVisible = ref(false)
const dialogTitle = ref('新增角色')
const submitLoading = ref(false)
const formRef = ref(null)
const treeRef = ref(null)
const isEdit = ref(false)
const currentRoleId = ref(null)

const form = reactive({
  role_name: '',
  description: '',
  perm_ids: [],
})

const formRules = {
  role_name: [
    { required: true, message: '请输入角色名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' },
  ],
}

// ==================== 权限树 ====================
const permissionTree = ref([])
const treeProps = {
  label: 'perm_name',
  children: 'children',
}

// ==================== 生命周期 ====================
onMounted(() => {
  loadRoles()
  loadPermissionTree()
})

// ==================== 数据加载 ====================
async function loadRoles() {
  loading.value = true
  try {
    const res = await getRoles({
      page: pagination.page,
      page_size: pagination.page_size,
      keyword: searchForm.keyword,
    })
    const data = res.data || {}
    roleList.value = data.items || []
    pagination.total = data.total || 0
  } catch (err) {
    ElMessage.error(err.message || '加载角色列表失败')
  } finally {
    loading.value = false
  }
}

async function loadPermissionTree() {
  try {
    const res = await getPermissionTree()
    permissionTree.value = res.data || []
  } catch (err) {
    ElMessage.error(err.message || '加载权限树失败')
  }
}

// ==================== 搜索与分页 ====================
function handleSearch() {
  pagination.page = 1
  loadRoles()
}

function handleReset() {
  searchForm.keyword = ''
  pagination.page = 1
  loadRoles()
}

function handleSizeChange(size) {
  pagination.page_size = size
  pagination.page = 1
  loadRoles()
}

function handlePageChange(page) {
  pagination.page = page
  loadRoles()
}

// ==================== 新增 / 编辑 ====================
function handleAdd() {
  isEdit.value = false
  currentRoleId.value = null
  dialogTitle.value = '新增角色'
  resetForm()
  dialogVisible.value = true
  nextTick(() => {
    treeRef.value?.setCheckedKeys([], false)
  })
}

async function handleEdit(row) {
  if (row.is_builtin) {
    ElMessage.warning('内置角色不允许编辑')
    return
  }
  isEdit.value = true
  currentRoleId.value = row.id
  dialogTitle.value = '编辑角色'
  resetForm()
  form.role_name = row.role_name
  form.description = row.description || ''
  dialogVisible.value = true

  // 加载该角色已有的权限
  try {
    const res = await getRolePermissions(row.id)
    const permIds = res.data || []
    nextTick(() => {
      treeRef.value?.setCheckedKeys(permIds, false)
    })
  } catch (err) {
    ElMessage.error(err.message || '加载角色权限失败')
  }
}

function resetForm() {
  form.role_name = ''
  form.description = ''
  form.perm_ids = []
  formRef.value?.resetFields()
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  // 收集选中的权限节点 ID
  const checkedKeys = treeRef.value?.getCheckedKeys(false) || []
  const halfCheckedKeys = treeRef.value?.getHalfCheckedKeys() || []
  form.perm_ids = [...new Set([...checkedKeys, ...halfCheckedKeys])]

  submitLoading.value = true
  try {
    const payload = {
      role_name: form.role_name,
      description: form.description,
      perm_ids: form.perm_ids,
    }
    if (isEdit.value) {
      await updateRole(currentRoleId.value, payload)
      ElMessage.success('角色更新成功')
    } else {
      await createRole(payload)
      ElMessage.success('角色创建成功')
    }
    dialogVisible.value = false
    loadRoles()
  } catch (err) {
    ElMessage.error(err.message || '提交失败')
  } finally {
    submitLoading.value = false
  }
}

// ==================== 删除 ====================
async function handleDelete(row) {
  if (row.is_builtin) {
    ElMessage.warning('内置角色不允许删除')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定要删除角色 "${row.role_name}" 吗？删除后不可恢复。`,
      '二次确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    await deleteRole(row.id)
    ElMessage.success('删除成功')
    loadRoles()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || '删除失败')
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

.perm-tree {
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 8px;
}
</style>
