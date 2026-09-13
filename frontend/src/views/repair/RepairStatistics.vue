<!--
维修统计页面 (RepairStatistics.vue)
3.7-F6 / FR-042
功能：
- 平均维修时长
- 工单状态分布
- 维修人员工作量
- 故障类型分布
- 故障设备TOP10
-->
<template>
  <div class="page-container">
    <!-- 概览卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <el-statistic title="工单总数" :value="overview.total_orders">
            <template #suffix>条</template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <el-statistic title="平均维修时长" :value="overview.avg_repair_hours" :precision="1">
            <template #suffix>小时</template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <el-statistic title="待处理" :value="getStatusCount('pending')">
            <template #suffix>条</template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <el-statistic title="已完成" :value="getStatusCount('completed')">
            <template #suffix>条</template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <!-- 状态分布 + 故障类型分布 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <span>工单状态分布</span>
          </template>
          <el-table :data="overview.status_distribution" stripe border size="small">
            <el-table-column prop="status" label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="statusType(row.status)" size="small">
                  {{ statusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="count" label="数量" align="center" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <span>故障类型分布（按设备类型）</span>
          </template>
          <el-table :data="faultTypes" stripe border size="small">
            <el-table-column prop="type" label="设备类型" min-width="140" show-overflow-tooltip />
            <el-table-column prop="count" label="工单数" width="100" align="center" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 维修人员工作量 + 故障设备TOP10 -->
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <span>维修人员工作量</span>
          </template>
          <el-table :data="workload" stripe border size="small">
            <el-table-column prop="name" label="维修人员" min-width="120" show-overflow-tooltip />
            <el-table-column prop="total" label="总工单" width="100" align="center" />
            <el-table-column prop="completed" label="已完成" width="100" align="center" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <span>故障设备 TOP10</span>
          </template>
          <el-table :data="top10Devices" stripe border size="small">
            <el-table-column type="index" label="排名" width="60" align="center" />
            <el-table-column prop="device_name" label="设备名称" min-width="140" show-overflow-tooltip />
            <el-table-column prop="device_code" label="设备编码" width="140" show-overflow-tooltip />
            <el-table-column prop="type_name" label="类型" width="100" show-overflow-tooltip />
            <el-table-column prop="fault_count" label="故障次数" width="90" align="center" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { getRepairOverview, getRepairerWorkload, getFaultDistribution, getTop10FaultDevices } from '@/api/repair'

const loading = ref(false)

const overview = reactive({
  total_orders: 0,
  avg_repair_hours: 0,
  status_distribution: [],
})

const workload = ref([])
const faultTypes = ref([])
const top10Devices = ref([])

onMounted(() => {
  loadAll()
})

async function loadAll() {
  loading.value = true
  try {
    const [overviewRes, workloadRes, faultRes, top10Res] = await Promise.all([
      getRepairOverview(),
      getRepairerWorkload(),
      getFaultDistribution(),
      getTop10FaultDevices(),
    ])

    // 后端已统一为响应信封 {code, message, data}（2026-09-13 迁移）。
    // 这 4 个统计接口原先是裸返回，本页读 `res.data` 拿到 undefined 后被
    // `|| {}` 兜底，4 项指标恒为 0/空——后端其实有数据。当时的临时修法是
    // 让前端改读裸对象（见上一提交），迁移后翻回信封读法。
    const ov = overviewRes.data || {}
    overview.total_orders = ov.total_orders || 0
    overview.avg_repair_hours = ov.avg_repair_hours || 0
    overview.status_distribution = ov.status_distribution || []

    workload.value = (workloadRes.data || {}).items || []
    faultTypes.value = (faultRes.data || {}).items || []
    top10Devices.value = (top10Res.data || {}).items || []
  } catch (err) {
    ElMessage.error(err.message || '加载统计数据失败')
  } finally {
    loading.value = false
  }
}

function getStatusCount(status) {
  const item = overview.status_distribution.find(d => d.status === status)
  return item ? item.count : 0
}

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
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20px;
}

.stat-row {
  margin-bottom: 16px;
}

.stat-card {
  text-align: center;
}
</style>
