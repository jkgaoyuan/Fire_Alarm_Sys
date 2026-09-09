<template>
  <el-dialog
    :model-value="modelValue"
    title="批量导入设备档案"
    width="720px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @open="handleOpen"
  >
    <el-alert type="info" :closable="false" class="import-tip">
      <template #title>
        请先下载模板，按列填写后上传。单次导入上限 5000 行，失败行会给出具体原因。
      </template>
    </el-alert>

    <div class="import-actions">
      <el-button link type="primary" :loading="templateLoading" @click="handleDownloadTemplate">
        <el-icon><download /></el-icon>
        下载导入模板
      </el-button>
    </div>

    <el-upload
      ref="uploadRef"
      drag
      :auto-upload="false"
      :limit="1"
      accept=".xlsx"
      :file-list="fileList"
      :on-change="handleFileChange"
      :on-exceed="handleExceed"
      :on-remove="handleRemove"
    >
      <el-icon class="el-icon--upload"><upload-filled /></el-icon>
      <div class="el-upload__text">将 Excel 文件拖到此处，或<em>点击选择</em></div>
      <template #tip>
        <div class="el-upload__tip">仅支持 .xlsx 格式的模板文件</div>
      </template>
    </el-upload>

    <div v-if="result" class="import-result">
      <el-alert
        :type="result.failed === 0 ? 'success' : result.rolled_back ? 'error' : 'warning'"
        :closable="false"
        show-icon
        :title="summaryText"
      />
      <el-table
        v-if="result.failures.length > 0"
        :data="result.failures"
        size="small"
        border
        max-height="240"
        class="failure-table"
      >
        <el-table-column prop="row" label="行号" width="80" align="center" />
        <el-table-column prop="device_code" label="设备编码" width="180" />
        <el-table-column prop="reason" label="失败原因" min-width="260" show-overflow-tooltip />
      </el-table>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
      <el-button
        type="primary"
        :disabled="!selectedFile"
        :loading="importing"
        @click="handleImport"
      >
        开始导入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, UploadFilled } from '@element-plus/icons-vue'
import { downloadImportTemplate, importDevices } from '@/api/device'

const emit = defineEmits(['update:modelValue', 'success'])
const props = defineProps({
  modelValue: { type: Boolean, default: false },
})

const TEMPLATE_FILE_NAME = '消防设备档案导入模板.xlsx'

const uploadRef = ref(null)
const selectedFile = ref(null)
const fileList = ref([])
const importing = ref(false)
const templateLoading = ref(false)
const result = ref(null)

const summaryText = computed(() => {
  if (!result.value) return ''
  const { total, success, failed, rolled_back: rolledBack } = result.value
  if (rolledBack) return `共 ${total} 行，失败 ${failed} 行已超过阈值，整批回滚未写入任何数据`
  return `共 ${total} 行，成功 ${success} 行，失败 ${failed} 行`
})

function handleOpen() {
  selectedFile.value = null
  fileList.value = []
  result.value = null
  uploadRef.value?.clearFiles()
}

function handleFileChange(file, files) {
  selectedFile.value = file.raw || null
  fileList.value = files
  result.value = null
}

function handleRemove() {
  selectedFile.value = null
  fileList.value = []
}

function handleExceed(files) {
  uploadRef.value?.clearFiles()
  const file = files[0]
  selectedFile.value = file
  fileList.value = [{ name: file.name, raw: file }]
}

async function handleDownloadTemplate() {
  templateLoading.value = true
  try {
    const blob = await downloadImportTemplate()
    const url = window.URL.createObjectURL(new Blob([blob]))
    const link = document.createElement('a')
    link.href = url
    link.download = TEMPLATE_FILE_NAME
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (err) {
    ElMessage.error(err.message || '模板下载失败')
  } finally {
    templateLoading.value = false
  }
}

async function handleImport() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择 Excel 文件')
    return
  }

  importing.value = true
  try {
    const res = await importDevices(selectedFile.value)
    result.value = res.data
    if (res.data.rolled_back) {
      ElMessage.error('失败率过高，本次导入已整体回滚')
    } else if (res.data.failed === 0) {
      ElMessage.success(`成功导入 ${res.data.success} 台设备`)
      emit('success')
    } else {
      ElMessage.warning(
        `成功导入 ${res.data.success} 台，失败 ${res.data.failed} 台，请修正失败行后重新上传`
      )
      emit('success')
    }
  } catch (err) {
    ElMessage.error(err.message || '导入失败')
  } finally {
    importing.value = false
  }
}
</script>

<style lang="scss" scoped>
.import-tip {
  margin-bottom: 12px;
}

.import-actions {
  margin-bottom: 8px;
}

.import-result {
  margin-top: 16px;
}

.failure-table {
  margin-top: 12px;
}
</style>
