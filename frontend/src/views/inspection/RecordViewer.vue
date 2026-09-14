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
import { computed, ref, watch } from 'vue'
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

// ⚠️ 必须是 computed 代理到 props.modelValue，**不能**写成 `const visible = ref(false)`。
// 那样写的话父组件传进来的 modelValue 只是被声明、从未被读，弹窗读的是另一个变量：
// 局部 ref 初值 false，唯一赋值是关闭时的 false，**没有任何路径能把它置为 true**，
// → 点「查看记录」永远不弹，而且不报错。
// 2026-09-14 实测缺陷。同病三处（本文件 / StatsDialog / PlanDetail），
// 已加静态守卫 tests/dialogContract.spec.js 拦住这一类。
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})
const loading = ref(false)
const recordList = ref([])

// 监听 prop 而不是监听 visible：打开时才拉取。
// ⚠️ 必须 immediate —— 只监听「变化」的话，若有调用方**挂载时就是打开状态**
// （modelValue 初值为 true），回调永远不会触发，弹窗开着但表格是空的。
// 加 immediate 后「初始即打开」与「关闭后再打开」两条路径都能拉到数据。
watch(
  () => props.modelValue,
  (val) => {
    if (val && props.taskId) {
      loadRecords()
    }
  },
  { immediate: true }
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
