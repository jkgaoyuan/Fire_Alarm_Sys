<template>
  <div class="plan-form">
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-width="140px"
      label-position="left"
    >
      <el-row :gutter="20">
        <!-- 基础信息 -->
        <el-col :span="12">
          <el-form-item label="预案名称" prop="plan_name">
            <el-input
              v-model="formData.plan_name"
              placeholder="请输入预案名称"
              maxlength="100"
              show-word-limit
            />
          </el-form-item>
        </el-col>
        
        <el-col :span="12">
          <el-form-item label="关联区域" prop="org_id">
            <el-select
              v-model="formData.org_id"
              placeholder="请选择区域"
              filterable
              style="width: 100%"
            >
              <el-option
                v-for="org in orgTree"
                :key="org.id"
                :label="org.org_name"
                :value="org.id"
              />
            </el-select>
          </el-form-item>
        </el-col>

        <el-col :span="12">
          <el-form-item label="火灾类型" prop="fire_type">
            <el-select v-model="formData.fire_type" placeholder="全部类型">
              <el-option label="不限制" :value="null" />
              <el-option label="A 类火警" value="fire" />
              <el-option label="预火灾" value="pre_fire" />
            </el-select>
          </el-form-item>
        </el-col>

        <el-col :span="12">
          <el-form-item label="触发报警类型" prop="trigger_alarm_type">
            <el-select v-model="formData.trigger_alarm_type" placeholder="全部类型">
              <el-option label="不限制" :value="null" />
              <el-option label="A 类火警" value="fire" />
              <el-option label="预火灾" value="pre_fire" />
              <el-option label="故障" value="fault" />
              <el-option label="屏蔽" value="shield" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <!-- 动作列表 -->
      <el-divider content-position="left">联动动作配置</el-divider>

      <el-form-item label="动作列表">
        <div v-for="(action, index) in formData.actions" :key="index" class="action-item">
          <el-card shadow="never" class="mb-8">
            <div class="action-header">
              <span class="action-number">{{ index + 1 }}</span>
              <el-button
                type="danger"
                size="small"
                @click="removeAction(index)"
                v-if="formData.actions.length > 1"
              >
                删除
              </el-button>
            </div>

            <el-row :gutter="16">
              <el-col :span="8">
                <el-form-item label="动作类型" required>
                  <el-select
                    v-model="action.action_type"
                    placeholder="选择动作"
                    style="width: 100%"
                  >
                    <el-option
                      v-for="type in actionTypes"
                      :key="type.value"
                      :label="type.label"
                      :value="type.value"
                    />
                  </el-select>
                </el-form-item>
              </el-col>

              <el-col :span="8">
                <el-form-item label="延迟执行 (秒)">
                  <el-input-number
                    v-model="action.delay_seconds"
                    :min="0"
                    :max="3600"
                    controls-position="right"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>

              <el-col :span="8">
                <el-form-item label="参数配置">
                  <el-button size="small" @click="editParams(action)">编辑</el-button>
                </el-form-item>
              </el-col>
            </el-row>

            <el-collapse-transition>
              <div v-show="action.expanded" class="params-editor">
                <el-form :inline="true" size="small">
                  <el-form-item label="Zone/区域">
                    <el-input v-model="action.params.zone" placeholder="例如：东侧" style="width: 200px" />
                  </el-form-item>
                  <el-form-item label="Door ID">
                    <el-input v-model="action.params.door_id" placeholder="例如：D-001" style="width: 200px" />
                  </el-form-item>
                  <el-form-item label="Area/区域">
                    <el-input v-model="action.params.area" placeholder="例如：大厅" style="width: 200px" />
                  </el-form-item>
                </el-form>
              </div>
            </el-collapse-transition>
          </el-card>
        </div>

        <el-button type="dashed" @click="addAction" style="width: 100%; margin-top: 16px">
          <i class="el-icon-plus" /> 添加联动动作
        </el-button>
      </el-form-item>

      <!-- 启用状态 -->
      <el-divider content-position="left">其他选项</el-divider>

      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item label="启用预案">
            <el-switch v-model="formData.is_enabled" />
          </el-form-item>
        </el-col>

        <el-col :span="12">
          <el-form-item label="允许模拟测试">
            <el-switch v-model="formData.is_simulation_allowed" />
          </el-form-item>
        </el-col>
      </el-row>

      <!-- 操作按钮 -->
      <el-form-item>
        <el-button type="primary" @click="handleSubmit">提交</el-button>
        <el-button @click="handleCancel">取消</el-button>
      </el-form-item>
    </el-form>

    <!-- 参数编辑器对话框 -->
    <el-dialog
      v-model="paramsDialogVisible"
      title="编辑动作参数"
      width="500px"
    >
      <el-input
        v-model="paramsJson"
        type="textarea"
        :rows="10"
        placeholder='{"zone": "东侧", "door_id": "D-001"}'
      />
      <template #footer>
        <el-button @click="paramsDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveParams">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="jsx">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  plan: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['submit', 'cancel'])

// 表单引用
const formRef = ref(null)

// 组织树（简化）
const orgTree = ref([
  { id: 1, org_name: '消防管理中心' },
])

// 动作类型
const actionTypes = [
  { value: 'start_exhaust', label: '启动排烟风机' },
  { value: 'close_door', label: '关闭防火门' },
  { value: 'start_lighting', label: '启动应急照明' },
  { value: 'broadcast', label: '播放疏散广播' },
]

// 表单数据
const formData = reactive({
  plan_name: '',
  org_id: null,
  fire_type: null,
  trigger_device_type_id: null,
  trigger_alarm_type: null,
  actions: [],
  is_enabled: true,
  is_simulation_allowed: true,
})

// 表单验证规则
const formRules = {
  plan_name: [
    { required: true, message: '请输入预案名称', trigger: 'blur' },
    { min: 1, max: 100, message: '长度在 1 到 100 个字符', trigger: 'blur' },
  ],
  org_id: [
    { required: true, message: '请选择关联区域', trigger: 'change' },
  ],
}

// 参数编辑器
const paramsDialogVisible = ref(false)
const currentEditAction = ref(null)
const paramsJson = ref('')

// 初始化表单
onMounted(() => {
  if (props.plan) {
    // 编辑模式
    Object.assign(formData, props.plan)
  } else {
    // 新建模式，添加一个默认动作
    addAction()
  }
})

// 添加动作
function addAction() {
  formData.actions.push({
    action_type: 'start_exhaust',
    delay_seconds: 0,
    params: {},
    expanded: false,
  })
}

// 删除动作
function removeAction(index) {
  formData.actions.splice(index, 1)
}

// 编辑参数
function editParams(action) {
  currentEditAction.value = action
  paramsJson.value = JSON.stringify(action.params || {}, null, 2)
  paramsDialogVisible.value = true
}

// 保存参数
function saveParams() {
  try {
    const params = JSON.parse(paramsJson.value)
    if (currentEditAction.value) {
      currentEditAction.value.params = params
    }
    paramsDialogVisible.value = false
    ElMessage.success('参数已保存')
  } catch (error) {
    ElMessage.error('JSON 格式错误，请检查')
  }
}

// 提交表单
async function handleSubmit() {
  try {
    await formRef.value.validate()
    
    // 确保至少有一个动作
    if (formData.actions.length === 0) {
      ElMessage.warning('请至少添加一个联动动作')
      return
    }
    
    emit('submit', { ...formData })
  } catch (error) {
    console.error('表单验证失败:', error)
  }
}

// 取消编辑
function handleCancel() {
  emit('cancel')
}

// Expose methods for parent
defineExpose({
  formData,
})
</script>

<style scoped lang="scss">
.plan-form {
  padding: 20px;
  
  .action-item {
    margin-bottom: 16px;
    
    .action-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      
      .action-number {
        font-size: 14px;
        font-weight: bold;
        color: #409eff;
      }
    }
    
    .params-editor {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid #ebeef5;
    }
  }
  
  .mb-8 {
    margin-bottom: 8px;
  }
}
</style>
