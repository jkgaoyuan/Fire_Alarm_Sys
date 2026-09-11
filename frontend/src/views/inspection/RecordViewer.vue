<!--
巡检记录查看 (RecordViewer)
3.6-F2 配套组件
功能：展示某任务的所有巡检记录
-->
<template>
  <el-dialog
    v-model="visible"
    :title="'巡检记录 - 任务 ID ' + taskId"
    width="900px"
  >
    <el-table
      v-loading="loading"
      :data="recordList"
      stripe
      border
    >
      <el-table-column prop="inspected_at" label="检查时间" width="180">
        <template #default="{ row }">
          {{ formatDateTime(row.inspected_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="device_code" label="设备编码" width="150" />
      <el-table-column prop="device_name" label="设备名称" min-width="180" />
      <el-table-column prop="result" label="结果" width="100">
        <template #default="{ row }">
          <el-tag :type="row.result === 'normal' ? 'success' : 'danger'">
            {{ recordStatusLabel(row.result) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="abnormal_desc" label="异常描述" min-width="200" show-overflow-tooltip />
      <el-table-column prop="photos" label="照片" width="150">
        <template #default="{ row }">
          <el-button link type="primary" @click="handlePreviewPhotos(row.photos)">
            查看（{{ (row.photos || []).length }}张）
          </el-button>
        </template>
      </el-table-column>
      <el-table-column prop="inspected_by_name" label="检查人" width="120" />
    </el-table>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getInspectionRecords } from '@/api/inspection'

const props = defineProps({
  modelValue: Boolean,
  taskId: {
    type: Number,
    default: null,
  },
})

const emit = defineEmits(['update:modelValue'])

const visible = ref(false)
const loading = ref(false)
const recordList = ref([])

watch(
  () => visible.value,
  (val) => {
    if (val && props.taskId) {
      loadRecords()
    }
  }
)

async function loadRecords() {
  loading.value = true
  try {
    const res = await getInspectionRecords({
      task_id: props.taskId,
      page: 1,
      page_size: 100,
    })
    const data = res.data || {}
    recordList.value = data.items || []
  } catch (err) {
    ElMessage.error('加载记录失败')
  } finally {
    loading.value = false
  }
}

function handleClose() {
  visible.value = false
}

function recordStatusLabel(result) {
  return result === 'normal' ? '正常' : '异常'
}

function formatDateTime(datetimeStr) {
  if (!datetimeStr) return '-'
  return datetimeStr.toString().replace('T', ' ').slice(0, 19)
}

function handlePreviewPhotos(photos) {
  if (!photos || photos.length === 0) return
  
  // 实际应实现图片预览弹窗
  ElMessage.info(`共 ${photos.length} 张照片`)
}
</script>
