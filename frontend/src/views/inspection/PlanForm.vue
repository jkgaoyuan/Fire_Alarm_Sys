<!--
巡检计划表单 (PlanForm)
3.6-F1 配套组件
功能：创建/编辑巡检计划
-->
<template>
  <el-dialog
    v-model="visible"
    :title="plan ? '编辑巡检计划' : '新增巡检计划'"
    width="600px"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-width="120px"
    >
      <el-form-item label="计划名称" prop="plan_name">
        <el-input
          v-model="formData.plan_name"
          placeholder="请输入计划名称"
          clearable
        />
      </el-form-item>

      <el-form-item label="所属区域" prop="org_id">
        <el-cascader
          v-model="formData.org_id"
          :options="orgOptions"
          :props="{ label: 'org_name', value: 'id', children: 'children', emitPath: false }"
          placeholder="选择区域"
          clearable
        />
      </el-form-item>

      <el-form-item label="设备类型" prop="device_type_id">
        <el-select
          v-model="formData.device_type_id"
          placeholder="全部类型（可选）"
          clearable
        >
          <el-option
            v-for="item in deviceTypes"
            :key="item.id"
            :label="item.type_name"
            :value="item.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="周期类型" prop="cycle_type">
        <el-radio-group v-model="formData.cycle_type">
          <el-radio-button value="daily">每日</el-radio-button>
          <el-radio-button value="weekly">每周</el-radio-button>
          <el-radio-button value="monthly">每月</el-radio-button>
          <el-radio-button value="quarterly">每季度</el-radio-button>
          <el-radio-button value="yearly">每年</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="责任人" prop="responsible_user_id">
        <el-select
          v-model="formData.responsible_user_id"
          placeholder="选择责任人"
          filterable
        >
          <el-option
            v-for="user in users"
            :key="user.id"
            :label="`${user.real_name} (${user.username})`"
            :value="user.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="开始日期" prop="start_date">
        <el-date-picker
          v-model="formData.start_date"
          type="date"
          placeholder="选择开始日期"
          style="width: 100%"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
        />
      </el-form-item>

      <el-form-item label="结束日期" prop="end_date">
        <el-date-picker
          v-model="formData.end_date"
          type="date"
          placeholder="选择结束日期（选填）"
          style="width: 100%"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
        />
      </el-form-item>

      <el-form-item label="启用状态">
        <el-switch v-model="formData.is_enabled" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="submitLoading">
        确定
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { createInspectionPlan, updateInspectionPlan } from '@/api/inspection'
import { getOrganizationTree } from '@/api/organization'
import { getDeviceTypes } from '@/api/device'
import { getUsers } from '@/api/user' // 使用正确的 API

const props = defineProps({
  modelValue: Boolean,
  plan: {
    type: Object,
    default: null,
  },
  orgOptions: {
    type: Array,
    default: () => [],
  },
  deviceTypes: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['update:modelValue', 'success'])

const formRef = ref()
const submitLoading = ref(false)

// v-model 同步：把外部 modelValue 双向绑定到弹窗 visible
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const users = ref([])

const formData = reactive({
  plan_name: '',
  org_id: null,
  device_type_id: null,
  cycle_type: 'daily',
  responsible_user_id: null,
  start_date: null,
  end_date: null,
  is_enabled: true,
})

const rules = {
  plan_name: [
    { required: true, message: '请输入计划名称', trigger: 'blur' },
    { max: 100, message: '不超过 100 字符', trigger: 'blur' },
  ],
  org_id: [{ required: true, message: '请选择所属区域', trigger: 'change' }],
  responsible_user_id: [
    { required: true, message: '请选择责任人', trigger: 'change' },
  ],
  start_date: [{ required: true, message: '请选择开始日期', trigger: 'change' }],
}

onMounted(() => {
  loadUsers()
})

defineExpose({
  setPlan(plan) {
    // 外部调用时设置计划数据
    Object.assign(formData, plan)
    formData.start_date = plan.start_date?.slice(0, 10) || null
    formData.end_date = plan.end_date?.slice(0, 10) || null
  },
})

// ==================== 辅助函数 ====================

async function loadUsers() {
  try {
    const res = await getUsers({ page: 1, page_size: 100 })
    users.value = res.data?.items || []
  } catch (err) {
    console.error('加载用户列表失败:', err)
  }
}

function handleClose() {
  visible.value = false
  formRef.value?.resetFields()
}

// ==================== 提交处理 ====================

async function handleSubmit() {
  try {
    await formRef.value.validate()

    const data = { ...formData }
    
    if (!data.end_date) {
      delete data.end_date
    }

    submitLoading.value = true
    
    let result
    if (props.plan) {
      // 编辑模式
      result = await updateInspectionPlan(props.plan.id, data)
    } else {
      // 新增模式
      result = await createInspectionPlan(data)
    }

    if (result.code === 200) {
      ElMessage.success(props.plan ? '更新成功' : '创建成功')
      emit('success')
      visible.value = false
    } else {
      ElMessage.error(result.message || '操作失败')
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
.el-form-item {
  margin-bottom: 20px;
}
</style>
