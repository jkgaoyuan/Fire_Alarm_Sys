<template>
  <div class="page-container">
    <h2>联动预案管理</h2>
    
    <!-- 筛选栏 -->
    <el-card class="filter-card">
      <el-form :model="filters" inline>
        <el-form-item label="区域">
          <el-select v-model="filters.org_id" placeholder="全部区域" clearable>
            <el-option label="全部" :value="null" />
            <el-option 
              v-for="org in orgTree" 
              :key="org.id" 
              :label="org.org_name" 
              :value="org.id" 
            />
          </el-select>
        </el-form-item>
        <el-form-item label="火灾类型">
          <el-select v-model="filters.fire_type" placeholder="全部类型" clearable>
            <el-option label="A 类火警" value="fire" />
            <el-option label="预火灾" value="pre_fire" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用状态">
          <el-select v-model="filters.is_enabled" placeholder="全部状态" clearable>
            <el-option label="已启用" :value="true" />
            <el-option label="已停用" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadPlans">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- 操作栏 -->
    <el-card class="table-card">
      <div class="table-toolbar">
        <el-button type="primary" @click="openCreateDialog">新建预案</el-button>
      </div>
      
      <!-- 预案列表 -->
      <el-table :data="plans" v-loading="loading" border stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="plan_name" label="预案名称" min-width="150" />
        <el-table-column label="关联区域" min-width="150">
          <template #default="{ row }">
            {{ row.organization?.org_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="fire_type" label="火灾类型" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.fire_type === 'fire'" type="danger">A 类火警</el-tag>
            <el-tag v-else-if="row.fire_type === 'pre_fire'" type="warning">预火灾</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="触发条件" min-width="200">
          <template #default="{ row }">
            <div v-if="row.trigger_alarm_type">
              {{ getAlarmTypeLabel(row.trigger_alarm_type) }}
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="动作数" width="100">
          <template #default="{ row }">
            {{ row.actions?.length || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="启用状态" width="100">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_enabled"
              @change="togglePlanStatus(row)"
              :active-value="true"
              :inactive-value="false"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetail(row)">详情</el-button>
            <el-button size="small" @click="editPlan(row)">编辑</el-button>
            <el-button size="small" type="warning" @click="simulateTrigger(row)">模拟测试</el-button>
            <el-button size="small" type="danger" @click="deletePlan(row)" v-if="!hasLogs(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 分页 -->
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="loadPlans"
        @current-change="loadPlans"
        style="margin-top: 20px; justify-content: flex-end"
      />
    </el-card>
    
    <!-- 新建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="700px"
    >
      <PlanForm
        ref="formRef"
        :plan="editingPlan"
        @submit="savePlan"
        @cancel="dialogVisible = false"
      />
    </el-dialog>
    
    <!-- 详情抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      title="预案详情"
      size="500px"
    >
      <div v-if="currentPlan">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="预案名称">{{ currentPlan.plan_name }}</el-descriptions-item>
          <el-descriptions-item label="关联区域">{{ currentPlan.organization?.org_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="火灾类型">
            <el-tag v-if="currentPlan.fire_type === 'fire'" type="danger">A 类火警</el-tag>
            <el-tag v-else-if="currentPlan.fire_type === 'pre_fire'" type="warning">预火灾</el-tag>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="触发条件">
            {{ currentPlan.trigger_alarm_type ? getAlarmTypeLabel(currentPlan.trigger_alarm_type) : '不限制' }}
          </el-descriptions-item>
          <el-descriptions-item label="动作列表">
            <ul v-for="(action, index) in currentPlan.actions" :key="index">
              <li>{{ formatActionType(action.action_type) }} - {{ formatActionParams(action.params) }}</li>
            </ul>
            <span v-if="!currentPlan.actions?.length">无动作</span>
          </el-descriptions-item>
          <el-descriptions-item label="启用状态">
            {{ currentPlan.is_enabled ? '启用' : '停用' }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="jsx">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PlanForm from './components/PlanForm.vue'
import * as LinkageApi from '@/api/linkage'

// 筛选条件
const filters = reactive({
  org_id: null,
  fire_type: null,
  is_enabled: null,
})

// 列表数据
const plans = ref([])
const loading = ref(false)
const pagination = reactive({
  page: 1,
  page_size: 10,
  total: 0,
})

// 表单相关
const dialogVisible = ref(false)
const editingPlan = ref(null)
const formRef = ref(null)

// 详情抽屉
const drawerVisible = ref(false)
const currentPlan = ref(null)

// 组织树（简化为数组）
const orgTree = ref([
  { id: 1, org_name: '消防管理中心' },
])

// 加载预案列表
async function loadPlans() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.page_size,
      ...filters,
    }
    const res = await LinkageApi.getLinkagePlans(params)
    
    if (res.code === 200) {
      plans.value = res.data.items
      pagination.total = res.data.total
    } else {
      ElMessage.error(res.message || '获取预案列表失败')
    }
  } catch (error) {
    console.error('加载预案列表失败:', error)
    ElMessage.error('获取预案列表失败')
  } finally {
    loading.value = false
  }
}

// 重置筛选
function resetFilters() {
  filters.org_id = null
  filters.fire_type = null
  filters.is_enabled = null
  pagination.page = 1
  loadPlans()
}

// 新建预案
function openCreateDialog() {
  editingPlan.value = null
  dialogVisible.value = true
}

// 编辑预案
function editPlan(plan) {
  editingPlan.value = { ...plan }
  dialogVisible.value = true
}

// 保存预案
async function savePlan(data) {
  try {
    if (editingPlan.value) {
      // 更新模式
      await LinkageApi.updateLinkagePlan(editingPlan.value.id, data)
      ElMessage.success('更新成功')
    } else {
      // 创建模式
      await LinkageApi.createLinkagePlan(data)
      ElMessage.success('创建成功')
    }
    
    dialogVisible.value = false
    loadPlans()
  } catch (error) {
    console.error('保存预案失败:', error)
    ElMessage.error('保存失败')
  }
}

// 切换启用状态
async function togglePlanStatus(plan) {
  try {
    await LinkageApi.togglePlanStatus(plan.id, plan.is_enabled)
    ElMessage.success(plan.is_enabled ? '已启用' : '已停用')
    loadPlans()
  } catch (error) {
    console.error('切换状态失败:', error)
    plan.is_enabled = !plan.is_enabled
    ElMessage.error('切换状态失败')
  }
}

// 查看详情
function viewDetail(plan) {
  currentPlan.value = plan
  drawerVisible.value = true
}

// 模拟触发
async function simulateTrigger(plan) {
  try {
    await LinkageApi.simulateTrigger(plan.id)
    ElMessage.success('模拟触发完成')
  } catch (error) {
    console.error('模拟触发失败:', error)
    ElMessage.error('模拟触发失败')
  }
}

// 删除预案
function deletePlan(plan) {
  ElMessageBox.confirm('确认删除该预案？此操作不可恢复', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(async () => {
    try {
      await LinkageApi.deleteLinkagePlan(plan.id)
      ElMessage.success('删除成功')
      loadPlans()
    } catch (error) {
      console.error('删除失败:', error)
      ElMessage.error('删除失败')
    }
  })
}

// 检查是否有日志
function hasLogs(planId) {
  // TODO: 调用 API 检查日志
  return false
}

// 工具函数
function getAlarmTypeLabel(type) {
  const labels = {
    fire: 'A 类火警',
    pre_fire: '预火灾',
    fault: '故障',
    shield: '屏蔽',
  }
  return labels[type] || type
}

function formatActionType(type) {
  const types = {
    start_exhaust: '启动排烟',
    close_door: '关闭防火门',
    start_lighting: '启动应急照明',
    broadcast: '疏散广播',
  }
  return types[type] || type
}

function formatActionParams(params) {
  if (!params) return ''
  return JSON.stringify(params)
}

onMounted(() => {
  loadPlans()
})
</script>

<style scoped lang="scss">
.page-container {
  padding: 20px;
  
  .filter-card,
  .table-card {
    margin-bottom: 20px;
  }
  
  .table-toolbar {
    margin-bottom: 16px;
  }
  
  ul {
    margin: 8px 0;
    padding-left: 20px;
  }
  
  li {
    margin: 4px 0;
  }
}
</style>
