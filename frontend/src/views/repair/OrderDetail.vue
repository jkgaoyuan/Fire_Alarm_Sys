<!--
维修工单详情 (OrderDetail.vue)
3.7-F1
功能：查看维修工单详情
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="维修工单详情"
    width="700px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-descriptions v-if="order" :column="2" border>
      <el-descriptions-item label="工单编号" :span="2">
        {{ order.order_no }}
      </el-descriptions-item>
      <el-descriptions-item label="设备名称">
        {{ order.device_name || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="设备编码">
        {{ order.device_code || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="当前状态" :span="2">
        <el-tag :type="statusType(order.status)">
          {{ statusLabel(order.status) }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="故障描述" :span="2">
        {{ order.fault_desc || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="报修人">
        {{ order.reporter_name || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="维修人员">
        {{ order.repairer_name || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="验收人">
        {{ order.acceptor_name || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="派单时间">
        {{ formatDateTime(order.assigned_at) }}
      </el-descriptions-item>
      <el-descriptions-item label="维修结果" :span="2">
        {{ order.repair_result || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="完成时间">
        {{ formatDateTime(order.completed_at) }}
      </el-descriptions-item>
      <el-descriptions-item label="验收时间">
        {{ formatDateTime(order.accepted_at) }}
      </el-descriptions-item>
      <el-descriptions-item v-if="order.return_reason" label="退回原因" :span="2">
        <span class="text-danger">{{ order.return_reason }}</span>
      </el-descriptions-item>
    </el-descriptions>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
defineProps({
  modelValue: { type: Boolean, default: false },
  order: { type: Object, default: null },
})

defineEmits(['update:modelValue', 'success'])

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

function formatDateTime(dt) {
  if (!dt) return '-'
  const d = new Date(dt)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const minute = String(d.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hour}:${minute}`
}
</script>

<style lang="scss" scoped>
.text-danger {
  color: #f56c6c;
}
</style>
