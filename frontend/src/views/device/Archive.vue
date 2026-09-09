<template>
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="search-card" shadow="never">
      <el-form :model="searchForm" inline>
        <el-form-item label="编码/名称">
          <el-input
            v-model="searchForm.keyword"
            placeholder="设备编码或名称"
            clearable
            style="width: 180px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="类型">
          <el-select
            v-model="searchForm.type_id"
            placeholder="全部类型"
            clearable
            style="width: 150px"
          >
            <el-option
              v-for="item in deviceTypes"
              :key="item.id"
              :label="item.type_name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="区域">
          <el-cascader
            v-model="searchForm.org_id"
            :options="orgOptions"
            :props="cascaderProps"
            placeholder="全部区域"
            clearable
            style="width: 200px"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="searchForm.status"
            placeholder="全部状态"
            multiple
            collapse-tags
            clearable
            style="width: 180px"
          >
            <el-option
              v-for="item in DEVICE_STATUS_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="品牌">
          <el-input
            v-model="searchForm.brand"
            placeholder="品牌"
            clearable
            style="width: 130px"
          />
        </el-form-item>
        <el-form-item label="显示已退役">
          <el-switch v-model="searchForm.include_retired" @change="handleSearch" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 设备列表 -->
    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>设备档案（共 {{ pagination.total }} 台）</span>
          <div>
            <PermissionButton
              permission="device:create"
              type="success"
              plain
              @click="importVisible = true"
            >
              <el-icon><upload /></el-icon>
              批量导入
            </PermissionButton>
            <PermissionButton
              permission="device:create"
              type="primary"
              @click="handleAdd"
            >
              <el-icon><plus /></el-icon>
              新增设备
            </PermissionButton>
          </div>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="deviceList"
        :row-class-name="rowClassName"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="device_code" label="设备编码" width="150" />
        <el-table-column prop="device_name" label="设备名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="type_name" label="类型" width="120" />
        <el-table-column prop="org_name" label="安装区域" width="140" show-overflow-tooltip />
        <el-table-column label="厂商/品牌" width="160" show-overflow-tooltip>
          <template #default="{ row }">
            {{ [row.manufacturer, row.brand].filter(Boolean).join(' / ') || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="install_date" label="安装日期" width="120" />
        <el-table-column prop="warranty_expire_date" label="质保到期" width="120" />
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="deviceStatusType(row.status)" size="small">
              {{ deviceStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-permission="'device:view'"
              link
              type="primary"
              @click="handleDetail(row)"
            >
              查看
            </el-button>
            <el-button
              v-if="!isTerminalStatus(row.status)"
              v-permission="'device:update'"
              link
              type="primary"
              @click="handleEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="!isTerminalStatus(row.status)"
              v-permission="'device:retire'"
              link
              type="warning"
              @click="handleRetire(row)"
            >
              退役
            </el-button>
            <el-button
              v-permission="'device:delete'"
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

    <ArchiveForm
      v-model="formVisible"
      :device="currentDevice"
      :device-types="deviceTypes"
      :org-options="orgOptions"
      @success="loadDevices"
    />
    <ArchiveImport v-model="importVisible" @success="loadDevices" />
    <ArchiveDetail
      v-model="detailVisible"
      :device-id="detailDeviceId"
      :device-types="deviceTypes"
    />
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload } from '@element-plus/icons-vue'
import PermissionButton from '@/components/PermissionButton.vue'
import ArchiveForm from './ArchiveForm.vue'
import ArchiveImport from './ArchiveImport.vue'
import ArchiveDetail from './ArchiveDetail.vue'
import { deleteDevice, getDevices, getDeviceTypes, retireDevice } from '@/api/device'
import { getOrganizationTree } from '@/api/organization'
import {
  DEVICE_STATUS_OPTIONS,
  deviceStatusLabel,
  deviceStatusType,
  isTerminalStatus,
  stripEmptyChildren,
} from '@/utils/device'

const cascaderProps = {
  label: 'org_name',
  value: 'id',
  children: 'children',
  checkStrictly: true,
  emitPath: false,
}

const loading = ref(false)
const deviceList = ref([])
const deviceTypes = ref([])
const orgOptions = ref([])

const searchForm = reactive({
  keyword: '',
  type_id: null,
  org_id: null,
  status: [],
  brand: '',
  include_retired: false,
})
const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const formVisible = ref(false)
const importVisible = ref(false)
const detailVisible = ref(false)
const currentDevice = ref(null)
const detailDeviceId = ref(null)

const route = useRoute()

onMounted(() => {
  loadDevices()
  loadDeviceTypes()
  loadOrgTree()
})

// 大屏 / 报警中心的「查看设备」跳转为 ?detail=<id>
watch(
  () => route.query.detail,
  (value) => {
    if (!value) return
    detailDeviceId.value = Number(value)
    detailVisible.value = true
  },
  { immediate: true }
)

// ==================== 数据加载 ====================

async function loadDevices() {
  loading.value = true
  try {
    const res = await getDevices({
      page: pagination.page,
      page_size: pagination.page_size,
      keyword: searchForm.keyword || undefined,
      type_id: searchForm.type_id || undefined,
      org_id: searchForm.org_id || undefined,
      brand: searchForm.brand || undefined,
      status: searchForm.status.length > 0 ? searchForm.status.join(',') : undefined,
      include_retired: searchForm.include_retired,
    })
    const data = res.data || {}
    deviceList.value = data.items || []
    pagination.total = data.total || 0
  } catch (err) {
    ElMessage.error(err.message || '加载设备列表失败')
  } finally {
    loading.value = false
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

async function loadOrgTree() {
  try {
    const res = await getOrganizationTree()
    orgOptions.value = stripEmptyChildren(res.data || [])
  } catch (err) {
    ElMessage.error(err.message || '加载组织架构失败')
  }
}

// ==================== 筛选与分页 ====================

function handleSearch() {
  pagination.page = 1
  loadDevices()
}

function handleReset() {
  searchForm.keyword = ''
  searchForm.type_id = null
  searchForm.org_id = null
  searchForm.status = []
  searchForm.brand = ''
  searchForm.include_retired = false
  handleSearch()
}

function handleSizeChange(size) {
  pagination.page_size = size
  pagination.page = 1
  loadDevices()
}

function handlePageChange(page) {
  pagination.page = page
  loadDevices()
}

function rowClassName({ row }) {
  return isTerminalStatus(row.status) ? 'retired-row' : ''
}

// ==================== 操作 ====================

function handleAdd() {
  currentDevice.value = null
  formVisible.value = true
}

function handleEdit(row) {
  currentDevice.value = row
  formVisible.value = true
}

function handleDetail(row) {
  detailDeviceId.value = row.id
  detailVisible.value = true
}

async function handleRetire(row) {
  try {
    const { value } = await ElMessageBox.prompt(
      `确定将设备「${row.device_name}（${row.device_code}）」退役吗？退役后不可再编辑，关联历史记录将完整保留。`,
      '设备退役',
      {
        confirmButtonText: '确定退役',
        cancelButtonText: '取消',
        inputPlaceholder: '请填写退役原因（选填）',
        inputValidator: (input) => (input || '').length <= 255 || '原因不超过 255 字',
      }
    )
    await retireDevice(row.id, { reason: value || undefined })
    ElMessage.success('设备已退役')
    loadDevices()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      ElMessage.error(err.message || '退役失败')
    }
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除设备「${row.device_name}（${row.device_code}）」的档案吗？删除后列表中不再显示，请优先使用「退役」。`,
      '二次确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }
    )
    await deleteDevice(row.id)
    ElMessage.success('删除成功')
    loadDevices()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
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

  :deep(.retired-row) {
    color: #a8abb2;

    .el-tag {
      opacity: 0.75;
    }
  }
}
</style>
