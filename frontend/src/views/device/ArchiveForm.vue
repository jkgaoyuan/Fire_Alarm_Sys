<template>
  <el-drawer
    :model-value="modelValue"
    :title="isEdit ? '编辑设备档案' : '新增设备档案'"
    size="640px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="formRules" label-width="110px">
      <el-form-item label="设备编码" prop="device_code">
        <el-input v-model="form.device_code" placeholder="如 DEV-SMK-001" />
      </el-form-item>
      <el-form-item label="设备名称" prop="device_name">
        <el-input v-model="form.device_name" placeholder="请输入设备名称" />
      </el-form-item>
      <el-form-item label="设备类型" prop="type_id">
        <el-select
          v-model="form.type_id"
          placeholder="请选择设备类型"
          clearable
          style="width: 100%"
          @change="handleTypeChange"
        >
          <el-option
            v-for="item in deviceTypes"
            :key="item.id"
            :label="item.type_name"
            :value="item.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="安装区域" prop="org_id">
        <el-cascader
          v-model="form.org_id"
          :options="orgOptions"
          :props="cascaderProps"
          placeholder="请选择安装区域"
          clearable
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="当前状态" prop="status">
        <el-select v-model="form.status" style="width: 100%">
          <el-option
            v-for="item in editableStatuses"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </el-form-item>

      <el-divider content-position="left">厂商信息</el-divider>
      <el-form-item label="厂商" prop="manufacturer">
        <el-input v-model="form.manufacturer" placeholder="生产厂商" />
      </el-form-item>
      <el-form-item label="品牌" prop="brand">
        <el-input v-model="form.brand" placeholder="品牌" />
      </el-form-item>
      <el-form-item label="型号" prop="model">
        <el-input v-model="form.model" placeholder="型号" />
      </el-form-item>
      <el-form-item label="规格" prop="spec">
        <el-input v-model="form.spec" placeholder="规格" />
      </el-form-item>

      <el-divider content-position="left">生命周期</el-divider>
      <el-form-item label="安装日期" prop="install_date">
        <el-date-picker
          v-model="form.install_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="质保到期" prop="warranty_expire_date">
        <el-date-picker
          v-model="form.warranty_expire_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="维护周期" prop="maintain_cycle">
        <el-input-number v-model="form.maintain_cycle" :min="0" :max="3650" controls-position="right" />
        <span class="unit-text">天</span>
      </el-form-item>

      <el-divider content-position="left">平面图坐标</el-divider>
      <el-form-item label="X 坐标" prop="map_x">
        <el-input-number v-model="form.map_x" :precision="2" :controls="false" style="width: 140px" />
      </el-form-item>
      <el-form-item label="Y 坐标" prop="map_y">
        <el-input-number v-model="form.map_y" :precision="2" :controls="false" style="width: 140px" />
      </el-form-item>

      <template v-if="attributeFields.length > 0">
        <el-divider content-position="left">扩展属性</el-divider>
        <el-form-item
          v-for="field in attributeFields"
          :key="field.key"
          :label="field.label"
        >
          <el-select
            v-if="field.type === 'select'"
            v-model="form.attributes[field.key]"
            clearable
            :placeholder="`请选择${field.label}`"
            style="width: 100%"
          >
            <el-option v-for="opt in field.options" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-input-number
            v-else-if="field.type === 'number'"
            v-model="form.attributes[field.key]"
            :controls="false"
            style="width: 100%"
          />
          <el-input
            v-else
            v-model="form.attributes[field.key]"
            :placeholder="`请输入${field.label}`"
          />
        </el-form-item>
      </template>

      <el-form-item label="备注" prop="remark">
        <el-input v-model="form.remark" type="textarea" :rows="3" maxlength="500" show-word-limit />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
        确定
      </el-button>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed, reactive, ref, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { createDevice, updateDevice, getDevices } from '@/api/device'
import { DEVICE_STATUS_OPTIONS, isTerminalStatus, mergeAttributes, resolveAttributeFields } from '@/utils/device'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  device: { type: Object, default: null },
  deviceTypes: { type: Array, default: () => [] },
  orgOptions: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'success'])

const formRef = ref(null)
const submitLoading = ref(false)

const isEdit = computed(() => Boolean(props.device?.id))
const cascaderProps = {
  label: 'org_name',
  value: 'id',
  children: 'children',
  checkStrictly: true,
  emitPath: false,
}
// retired 只能通过「退役」按钮产生，表单里不开放
const editableStatuses = DEVICE_STATUS_OPTIONS.filter(
  (item) => !isTerminalStatus(item.value)
)

function createEmptyForm() {
  return {
    device_code: '',
    device_name: '',
    type_id: null,
    org_id: null,
    status: 'normal',
    manufacturer: '',
    brand: '',
    model: '',
    spec: '',
    install_date: '',
    warranty_expire_date: '',
    maintain_cycle: null,
    map_x: null,
    map_y: null,
    remark: '',
    attributes: {},
  }
}

const form = reactive(createEmptyForm())

const currentSchema = computed(() => {
  const type = props.deviceTypes.find((item) => item.id === form.type_id)
  return type?.attribute_schema || {}
})
const attributeFields = computed(() => resolveAttributeFields(currentSchema.value))

/** 编码唯一性异步校验：命中同名编码且不是本条记录时判为冲突 */
async function validateCodeUnique(rule, value) {
  if (!value) return
  let items = []
  try {
    const res = await getDevices({ keyword: value, page_size: 100, include_retired: true })
    items = res.data?.items || []
  } catch {
    // 校验服务不可用时不阻塞用户提交，由后端最终裁决
    return
  }
  const conflict = items.some(
    (item) => item.device_code === value && item.id !== props.device?.id
  )
  if (conflict) throw new Error(`设备编码已存在: ${value}`)
}

const formRules = {
  device_code: [
    { required: true, min: 1, max: 100, message: '请输入设备编码', trigger: 'blur' },
    { validator: validateCodeUnique, trigger: 'blur' },
  ],
  device_name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
}

function fillForm() {
  const base = createEmptyForm()
  const source = props.device || {}
  for (const key of Object.keys(base)) {
    const value = source[key]
    form[key] = value === undefined || value === null ? base[key] : value
  }
  form.attributes = mergeAttributes(currentSchema.value, source.attributes)
  nextTick(() => formRef.value?.clearValidate())
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) fillForm()
  }
)

function handleTypeChange() {
  form.attributes = mergeAttributes(currentSchema.value, {})
}

function buildPayload() {
  const payload = { ...form, attributes: { ...form.attributes } }
  for (const key of ['manufacturer', 'brand', 'model', 'spec', 'remark']) {
    if (!payload[key]) delete payload[key]
  }
  for (const key of ['install_date', 'warranty_expire_date']) {
    if (!payload[key]) payload[key] = null
  }
  return payload
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  const payload = buildPayload()
  submitLoading.value = true
  try {
    if (isEdit.value) {
      await updateDevice(props.device.id, payload)
      ElMessage.success('设备档案已更新')
    } else {
      await createDevice(payload)
      ElMessage.success('设备档案已创建')
    }
    emit('update:modelValue', false)
    emit('success')
  } catch (err) {
    ElMessage.error(err.message || '提交失败')
  } finally {
    submitLoading.value = false
  }
}
</script>

<style lang="scss" scoped>
.unit-text {
  margin-left: 8px;
  color: #909399;
}
</style>
