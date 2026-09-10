<!--
维修工单创建表单 (OrderForm.vue)
3.7-F1
功能：创建维修工单
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="创建维修工单"
    width="600px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="handleOpen"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="100px"
    >
      <el-form-item label="故障设备" prop="device_id">
        <el-select
          v-model="form.device_id"
          placeholder="请选择设备"
          filterable
          remote
          :remote-method="searchDevices"
          :loading="deviceLoading"
          style="width: 100%"
        >
          <el-option
            v-for="device in deviceOptions"
            :key="device.id"
            :label="`${device.device_name} (${device.device_code})`"
            :value="device.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="故障描述" prop="fault_desc">
        <el-input
          v-model="form.fault_desc"
          type="textarea"
          :rows="4"
          placeholder="请详细描述故障现象"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        确定
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createRepairOrder } from '@/api/repair'
import { getDevices } from '@/api/device'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'success'])

const formRef = ref(null)
const submitting = ref(false)
const deviceLoading = ref(false)
const deviceOptions = ref([])

const form = reactive({
  device_id: null,
  fault_desc: '',
})

const rules = {
  device_id: [{ required: true, message: '请选择故障设备', trigger: 'change' }],
  fault_desc: [{ required: true, message: '请输入故障描述', trigger: 'blur' }],
}

function handleOpen() {
  // 重置表单
  form.device_id = null
  form.fault_desc = ''
  formRef.value?.resetFields()
  // 加载默认设备列表
  searchDevices('')
}

async function searchDevices(keyword) {
  deviceLoading.value = true
  try {
    const res = await getDevices({
      page: 1,
      page_size: 50,
      keyword: keyword || undefined,
    })
    const data = res.data || {}
    deviceOptions.value = data.items || []
  } catch (err) {
    ElMessage.error('加载设备列表失败')
  } finally {
    deviceLoading.value = false
  }
}

async function handleSubmit() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    await createRepairOrder({
      device_id: form.device_id,
      fault_desc: form.fault_desc,
    })
    ElMessage.success('工单创建成功')
    emit('update:modelValue', false)
    emit('success')
  } catch (err) {
    ElMessage.error(err.message || '创建失败')
  } finally {
    submitting.value = false
  }
}
</script>
