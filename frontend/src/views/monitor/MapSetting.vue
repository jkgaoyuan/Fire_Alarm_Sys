<template>
  <el-drawer
    :model-value="modelValue"
    title="平面图配置"
    size="620px"
    @update:model-value="emit('update:modelValue', $event)"
    @open="loadAll"
  >
    <el-alert
      type="info"
      :closable="false"
      class="map-setting__tip"
      title="平面图挂在楼层节点，区域叶子节点自动继承；宽超过 2000px 会等比压缩，设备点位按压缩后的基准尺寸换算"
    />

    <el-form label-position="top">
      <el-form-item label="目标楼层">
        <el-cascader
          v-model="orgId"
          :options="orgOptions"
          :props="cascaderProps"
          placeholder="选择楼层节点"
          style="width: 100%"
          @change="loadMeta"
        />
      </el-form-item>
    </el-form>

    <div v-if="meta" class="map-setting__current">
      <div class="map-setting__row">
        <span>所属层级：</span>
        <span>{{ meta.resolved_org_name || '本节点尚未上传' }}</span>
        <el-tag v-if="inheritsFromParent" size="small" type="warning" effect="plain">
          继承自上级
        </el-tag>
      </div>
      <template v-if="meta.map_image_url">
        <img :src="meta.map_image_url" alt="平面图预览" class="map-setting__preview" />
        <div class="map-setting__row map-setting__dim">
          基准尺寸 {{ meta.map_image_width }} × {{ meta.map_image_height }} px（{{ meta.map_origin }}）
        </div>
        <el-button v-permission="'monitor:config'" type="danger" plain :loading="deleting" @click="handleDelete">
          移除平面图
        </el-button>
      </template>
      <el-empty v-else :image-size="60" description="该楼层暂无平面图" />
    </div>

    <el-upload
      v-permission="'monitor:config'"
      class="map-setting__upload"
      drag
      :disabled="uploading"
      :show-file-list="false"
      :accept="ACCEPT"
      :before-upload="validateFile"
      :http-request="handleUpload"
    >
      <div class="map-setting__drag">
        <div v-if="uploading">上传并压缩中…</div>
        <div v-else>将平面图拖到此处，或<em>点击选择文件</em></div>
        <div class="map-setting__dim">支持 PNG / JPG / PDF（取首页），单文件不超过 10MB</div>
      </div>
    </el-upload>
  </el-drawer>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteMapImage, getOrganizationTree, uploadMapImage } from '@/api/organization'
import { getMapMeta } from '@/api/monitor'
import { stripEmptyChildren } from '@/utils/device'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** 打开时定位到的区域（会向上解析到所属楼层） */
  orgId: { type: Number, default: null },
})
const emit = defineEmits(['update:modelValue', 'success'])

const ACCEPT = '.png,.jpg,.jpeg,.pdf'
const MAX_SIZE_MB = 10
const ALLOWED_EXT = ['png', 'jpg', 'jpeg', 'pdf']

const orgOptions = ref([])
const orgId = ref(props.orgId || null)
const meta = ref(null)
const uploading = ref(false)
const deleting = ref(false)

const cascaderProps = {
  label: 'org_name',
  value: 'id',
  children: 'children',
  // 楼层下仍有区域子节点，不开 checkStrictly 就选不到 floor 本身
  checkStrictly: true,
  emitPath: false,
  // 平面图只挂 floor 节点，其余层级仅用于展开定位（计划 5.4 继承规则）
  disabled: (node) => node.org_type !== 'floor',
}

const inheritsFromParent = computed(
  () => !!meta.value?.resolved_org_id && meta.value.resolved_org_id !== meta.value.org_id
)

async function loadAll() {
  orgId.value = props.orgId || orgId.value
  try {
    const res = await getOrganizationTree()
    orgOptions.value = stripEmptyChildren(res.data || [])
  } catch (err) {
    ElMessage.error(err.message || '加载组织架构失败')
  }
  await loadMeta()
}

async function loadMeta() {
  meta.value = null
  if (!orgId.value) return
  try {
    const res = await getMapMeta(orgId.value)
    meta.value = res.data
  } catch (err) {
    ElMessage.error(err.message || '加载平面图信息失败')
  }
}

function validateFile(file) {
  const ext = (file.name.split('.').pop() || '').toLowerCase()
  if (!ALLOWED_EXT.includes(ext)) {
    ElMessage.error('仅支持 PNG / JPG / PDF 文件')
    return false
  }
  if (file.size > MAX_SIZE_MB * 1024 * 1024) {
    ElMessage.error(`文件不能超过 ${MAX_SIZE_MB}MB`)
    return false
  }
  return true
}

async function handleUpload({ file }) {
  if (!orgId.value) {
    ElMessage.warning('请先选择目标楼层')
    return
  }
  uploading.value = true
  try {
    const res = await uploadMapImage(orgId.value, file)
    meta.value = { ...meta.value, ...(res.data || {}) }
    ElMessage.success('平面图已上传')
    emit('success', res.data)
  } catch (err) {
    ElMessage.error(err.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function handleDelete() {
  if (!orgId.value) return
  try {
    await ElMessageBox.confirm(
      '移除后该楼层及其下所有区域的地图点位将不再显示，确定继续吗？',
      '移除平面图',
      { type: 'warning', confirmButtonText: '确定移除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  deleting.value = true
  try {
    await deleteMapImage(orgId.value)
    await loadMeta()
    ElMessage.success('平面图已移除')
    emit('success', null)
  } catch (err) {
    ElMessage.error(err.message || '移除失败')
  } finally {
    deleting.value = false
  }
}
</script>

<style lang="scss" scoped>
.map-setting {
  &__tip {
    margin-bottom: 16px;
  }

  &__current {
    margin-bottom: 16px;
  }

  &__row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    font-size: 13px;
  }

  &__preview {
    display: block;
    max-width: 100%;
    max-height: 260px;
    border: 1px solid #ebeef5;
    border-radius: 4px;
    margin-bottom: 8px;
  }

  &__dim {
    color: #909399;
    font-size: 12px;
  }

  &__drag {
    padding: 16px 0;
  }

  &__upload {
    width: 100%;
  }
}
</style>
