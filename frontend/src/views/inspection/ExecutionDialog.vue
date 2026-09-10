<!--
执行巡检弹窗 (ExecutionDialog)
3.6-F2 配套组件
功能：提交巡检记录表单
-->
<template>
  <el-dialog
    v-model="visible"
    title="提交巡检记录"
    width="700px"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-width="100px"
    >
      <!-- 设备列表 -->
      <el-divider content-position="left">选择设备</el-divider>
      
      <el-input
        v-model="deviceSearch"
        placeholder="搜索设备编码/名称"
        clearable
        style="margin-bottom: 12px"
      />
      
      <el-table
        :data="filteredDevices"
        highlight-current-row
        @current-change="handleDeviceSelect"
      >
        <el-table-column prop="device_code" label="编码" width="150" />
        <el-table-column prop="device_name" label="名称" min-width="180" />
        <el-table-column prop="type_name" label="类型" width="120" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="deviceStatusType(row.status)" size="small">
              {{ deviceStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <!-- 巡检结果 -->
      <el-divider content-position="left">巡检信息</el-divider>
      
      <el-form-item label="巡检结果" prop="result">
        <el-radio-group v-model="formData.result">
          <el-radio-button value="normal">正常</el-radio-button>
          <el-radio-button value="abnormal">异常</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="异常情况" prop="abnormal_desc">
        <el-input
          v-model="formData.abnormal_desc"
          type="textarea"
          :rows="3"
          placeholder="请输入异常描述（仅异常时填写）"
          show-word-limit
          maxlength="500"
        />
      </el-form-item>

      <!-- 照片上传 -->
      <el-form-item label="现场照片" prop="photos">
        <el-upload
          action="#"
          list-type="picture-card"
          :on-remove="handleRemovePhoto"
          :on-preview="handlePreviewPhoto"
          :limit="5"
        >
          <el-icon><Plus /></el-icon>
          <template #file="{ file }">
            <img :src="file.url" class="el-upload-list__item-thumbnail" />
            <span class="el-upload-list__item-name">
              {{ file.name }}
            </span>
          </template>
        </el-upload>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="submitLoading">
        提交记录
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { submitInspectionRecord } from '@/API/inspection'
import { getDevices } from '@/api/device'
import {
  deviceStatusLabel,
  deviceStatusType,
} from '@/utils/device'

const props = defineProps({
  modelValue: Boolean,
  taskId: {
    type: Number,
    default: null,
  },
})

const emit = defineEmits(['update:modelValue', 'success'])

const visible = ref(false)
const formRef = ref()
const submitLoading = ref(false)
const deviceSearch = ref('')
const currentSelectedDevice = ref(null)
const allDevices = ref([])

const formData = reactive({
  result: 'normal',
  abnormal_desc: '',
  photos: [],
})

const rules = {
  result: [{ required: true, message: '请选择巡检结果', trigger: 'change' }],
}

watch(
  () => props.taskId,
  (taskId) => {
    if (taskId) {
      loadDevices()
    }
  }
)

// ==================== 数据加载 ====================

async function loadDevices() {
  try {
    const res = await getDevices({ page: 1, page_size: 100 })
    allDevices.value = res.data?.items || []
  } catch (err) {
    ElMessage.error('加载设备列表失败')
  }
}

// ==================== 计算属性 ====================

const filteredDevices = computed(() => {
  if (!deviceSearch.value) return allDevices.value
  const keyword = deviceSearch.value.toLowerCase()
  return allDevices.value.filter(
    (d) =>
      d.device_code.toLowerCase().includes(keyword) ||
      d.device_name.toLowerCase().includes(keyword)
  )
})

// ==================== 事件处理 ====================

function handleClose() {
  visible.value = false
  formRef.value?.resetFields()
  emit('success')
}

function handleDeviceSelect(device) {
  currentSelectedDevice.value = device
}

function handleRemovePhoto() {
  // 从 photos 数组中移除
}

function handlePreviewPhoto() {
  // 预览照片
}

async function handleSubmit() {
  if (!currentSelectedDevice.value) {
    ElMessage.warning('请先选择设备')
    return
  }

  try {
    await formRef.value.validate()

    const data = {
      task_id: props.taskId,
      device_id: currentSelectedDevice.value.id,
      result: formData.result,
      abnormal_desc: formData.abnormal_desc || null,
      photos: [], // 实际应上传文件后获取 URL
    }

    submitLoading.value = true
    
    const response = await submitInspectionRecord(props.taskId, data)
    
    if (response.code === 200) {
      ElMessage.success('记录提交成功')
      emit('success')
      visible.value = false
    } else {
      ElMessage.error(response.message || '提交失败')
    }
  } catch (error) {
    if (error !== false) {
      console.error('表单验证失败:', error)
    }
  } finally {
    submitLoading.value = false
  }
}
</script>

<style lang="scss" scoped>
.el-divider {
  margin-bottom: 24px;
}

:deep(.el-upload-list__item) {
  width: 100px;
  height: 100px;
}

:deep(.el-upload-list__item-name) {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
