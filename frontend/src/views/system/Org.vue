<template>
  <div class="page-container org-page">
    <!-- 左侧组织架构树 -->
    <el-card class="org-tree-card" shadow="never">
      <template #header>
        <div class="tree-header">
          <span>组织架构</span>
          <el-button
            v-permission="'system:org:create'"
            type="primary"
            size="small"
            @click="handleAddRoot"
          >
            新增根节点
          </el-button>
        </div>
      </template>
      <el-tree
        ref="treeRef"
        :data="orgTree"
        :props="{ label: 'org_name', children: 'children' }"
        node-key="id"
        highlight-current
        default-expand-all
        @node-click="handleNodeClick"
      >
        <template #default="{ node, data }">
          <span class="tree-node">
            <el-icon v-if="data.org_type === 'building'"><OfficeBuilding /></el-icon>
            <el-icon v-else-if="data.org_type === 'floor'"><HomeFilled /></el-icon>
            <el-icon v-else><MapLocation /></el-icon>
            <span class="node-label">{{ node.label }}</span>
            <el-tag size="small" :type="typeTagType(data.org_type)">
              {{ typeLabel(data.org_type) }}
            </el-tag>
          </span>
        </template>
      </el-tree>
    </el-card>

    <!-- 右侧表单 -->
    <div class="org-form-area">
      <el-card v-if="formMode !== 'none'" shadow="never">
        <template #header>
          <div class="card-header">
            <span>{{ formTitle }}</span>
          </div>
        </template>

        <el-form
          ref="formRef"
          :model="formData"
          :rules="formRules"
          label-width="100px"
        >
          <el-form-item label="节点名称" prop="org_name">
            <el-input
              v-model="formData.org_name"
              placeholder="请输入节点名称"
              maxlength="100"
              show-word-limit
            />
          </el-form-item>

          <el-form-item label="节点类型" prop="org_type">
            <el-select
              v-model="formData.org_type"
              placeholder="请选择类型"
              style="width: 100%"
            >
              <el-option label="建筑" value="building" />
              <el-option label="楼层" value="floor" />
              <el-option label="区域" value="zone" />
            </el-select>
          </el-form-item>

          <el-form-item label="父节点">
            <el-cascader
              v-model="formData.parent_id"
              :options="parentOptions"
              :props="{
                label: 'org_name',
                value: 'id',
                children: 'children',
                checkStrictly: true,
                emitPath: false,
              }"
              placeholder="不选则为根节点"
              clearable
              style="width: 100%"
            />
          </el-form-item>

          <el-form-item label="排序">
            <el-input-number
              v-model="formData.sort_order"
              :min="0"
              :max="999"
              style="width: 100%"
            />
          </el-form-item>

          <el-form-item>
            <el-button type="primary" :loading="saving" @click="handleSave">
              保存
            </el-button>
            <el-button v-if="formMode === 'edit'" @click="handleAddChild">
              新增子节点
            </el-button>
            <el-button
              v-if="formMode === 'edit'"
              type="danger"
              plain
              @click="handleDelete"
            >
              删除
            </el-button>
            <el-button @click="handleCancel">取消</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 楼层平面图 -->
      <el-card
        v-if="formMode === 'edit' && formData.org_type === 'floor'"
        class="map-card"
        shadow="never"
      >
        <template #header>
          <div class="card-header">
            <span>楼层平面图</span>
          </div>
        </template>

        <div v-if="mapMeta?.map_image_url" class="map-preview-wrapper">
          <img
            :src="mapMeta.map_image_url"
            alt="平面图预览"
            class="map-preview-img"
          />
          <div class="map-dim">
            基准尺寸 {{ mapMeta.map_image_width }} × {{ mapMeta.map_image_height }} px
          </div>
          <el-button
            v-permission="'monitor:config'"
            type="danger"
            plain
            :loading="mapDeleting"
            @click="handleDeleteMap"
          >
            移除平面图
          </el-button>
        </div>
        <el-empty v-else description="该楼层暂无平面图" />

        <el-upload
          v-permission="'monitor:config'"
          class="map-uploader"
          drag
          :disabled="mapUploading"
          :show-file-list="false"
          accept=".png,.jpg,.jpeg,.pdf"
          :before-upload="validateMapFile"
          :http-request="handleMapUpload"
        >
          <div v-if="mapUploading">上传并压缩中…</div>
          <div v-else>
            将平面图拖到此处，或<em>点击选择文件</em>
          </div>
          <div class="map-tip">支持 PNG / JPG / PDF，单文件不超过 10MB</div>
        </el-upload>
      </el-card>

      <!-- 空状态 -->
      <el-empty
        v-if="formMode === 'none'"
        description="请在左侧选择或新建节点"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { OfficeBuilding, HomeFilled, MapLocation } from '@element-plus/icons-vue'
import {
  createOrganization,
  deleteOrganization,
  getOrganizationTree,
  updateOrganization,
  uploadMapImage,
  deleteMapImage,
} from '@/api/organization'
import { getMapMeta } from '@/api/monitor'

const treeRef = ref()
const formRef = ref()
const orgTree = ref([])
const loading = ref(false)
const saving = ref(false)
const formMode = ref('none') // 'none' | 'add' | 'edit'
const mapMeta = ref(null)
const mapUploading = ref(false)
const mapDeleting = ref(false)

const formData = ref({
  id: null,
  org_name: '',
  org_type: '',
  parent_id: null,
  sort_order: 0,
})

const formRules = {
  org_name: [{ required: true, message: '请输入节点名称', trigger: 'blur' }],
  org_type: [{ required: true, message: '请选择节点类型', trigger: 'change' }],
}

const formTitle = computed(() => {
  if (formMode.value === 'add') return '新增节点'
  if (formMode.value === 'edit') return '编辑节点'
  return ''
})

// 父节点级联选项：排除当前节点及其子树，避免循环引用
const parentOptions = computed(() => {
  if (formMode.value !== 'edit' || !formData.value.id) return orgTree.value
  return filterTree(orgTree.value, formData.value.id)
})

function typeLabel(type) {
  const map = { building: '建筑', floor: '楼层', zone: '区域' }
  return map[type] || type
}

function typeTagType(type) {
  const map = { building: 'primary', floor: 'success', zone: 'info' }
  return map[type] || ''
}

function filterTree(nodes, excludeId) {
  return nodes
    .filter((n) => n.id !== excludeId)
    .map((n) => {
      const clone = { ...n }
      if (n.children?.length) {
        clone.children = filterTree(n.children, excludeId)
      }
      return clone
    })
}

async function loadTree() {
  loading.value = true
  try {
    const res = await getOrganizationTree()
    orgTree.value = res.data || []
  } catch (err) {
    ElMessage.error(err.message || '加载组织架构失败')
  } finally {
    loading.value = false
  }
}

function handleNodeClick(data) {
  formMode.value = 'edit'
  formData.value = {
    id: data.id,
    org_name: data.org_name,
    org_type: data.org_type,
    parent_id: data.parent_id,
    sort_order: data.sort_order ?? 0,
  }
  loadMapMeta(data.id)
}

function handleAddRoot() {
  formMode.value = 'add'
  formData.value = {
    id: null,
    org_name: '',
    org_type: '',
    parent_id: null,
    sort_order: 0,
  }
  mapMeta.value = null
  nextTick(() => formRef.value?.resetFields())
}

function handleAddChild() {
  const parentId = formData.value.id
  formMode.value = 'add'
  formData.value = {
    id: null,
    org_name: '',
    org_type: '',
    parent_id: parentId,
    sort_order: 0,
  }
  mapMeta.value = null
  nextTick(() => formRef.value?.resetFields())
}

function handleCancel() {
  formMode.value = 'none'
  formData.value = { id: null, org_name: '', org_type: '', parent_id: null, sort_order: 0 }
  mapMeta.value = null
}

async function handleSave() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  saving.value = true
  try {
    const payload = {
      org_name: formData.value.org_name,
      org_type: formData.value.org_type,
      parent_id: formData.value.parent_id || null,
      sort_order: formData.value.sort_order,
    }

    if (formMode.value === 'edit' && formData.value.id) {
      await updateOrganization(formData.value.id, payload)
      ElMessage.success('更新成功')
    } else {
      const res = await createOrganization(payload)
      formData.value.id = res.data?.id
      formMode.value = 'edit'
      ElMessage.success('创建成功')
    }
    await loadTree()
  } catch (err) {
    ElMessage.error(err.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (!formData.value.id) return
  try {
    await ElMessageBox.confirm(
      `确定删除节点「${formData.value.org_name}」吗？其子节点也会一并删除。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  try {
    await deleteOrganization(formData.value.id)
    ElMessage.success('删除成功')
    handleCancel()
    await loadTree()
  } catch (err) {
    ElMessage.error(err.message || '删除失败')
  }
}

async function loadMapMeta(orgId) {
  if (!orgId || formData.value.org_type !== 'floor') {
    mapMeta.value = null
    return
  }
  try {
    const res = await getMapMeta(orgId)
    mapMeta.value = res.data
  } catch {
    mapMeta.value = null
  }
}

function validateMapFile(file) {
  const ext = (file.name.split('.').pop() || '').toLowerCase()
  const allowed = ['png', 'jpg', 'jpeg', 'pdf']
  if (!allowed.includes(ext)) {
    ElMessage.error('仅支持 PNG / JPG / PDF 文件')
    return false
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('文件不能超过 10MB')
    return false
  }
  return true
}

async function handleMapUpload({ file }) {
  if (!formData.value.id) {
    ElMessage.warning('请先保存节点')
    return
  }
  mapUploading.value = true
  try {
    const res = await uploadMapImage(formData.value.id, file)
    mapMeta.value = res.data
    ElMessage.success('平面图上传成功')
  } catch (err) {
    ElMessage.error(err.message || '上传失败')
  } finally {
    mapUploading.value = false
  }
}

async function handleDeleteMap() {
  if (!formData.value.id) return
  try {
    await ElMessageBox.confirm('移除后该楼层及其下所有区域的地图点位将不再显示，确定继续吗？', '移除平面图', {
      type: 'warning',
    })
  } catch {
    return
  }
  mapDeleting.value = true
  try {
    await deleteMapImage(formData.value.id)
    mapMeta.value = null
    ElMessage.success('平面图已移除')
  } catch (err) {
    ElMessage.error(err.message || '移除失败')
  } finally {
    mapDeleting.value = false
  }
}

loadTree()
</script>

<style lang="scss" scoped>
.org-page {
  display: flex;
  gap: 16px;
  padding: 20px;

  .org-tree-card {
    width: 320px;
    flex-shrink: 0;

    .tree-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .tree-node {
      display: flex;
      align-items: center;
      gap: 6px;

      .node-label {
        flex: 1;
      }
    }
  }

  .org-form-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 16px;

    .map-card {
      .map-preview-wrapper {
        text-align: center;

        .map-preview-img {
          max-width: 100%;
          max-height: 300px;
          border: 1px solid #ebeef5;
          border-radius: 4px;
        }

        .map-dim {
          margin: 8px 0;
          color: #909399;
          font-size: 12px;
        }
      }

      .map-uploader {
        margin-top: 16px;

        .map-tip {
          color: #909399;
          font-size: 12px;
        }
      }
    }
  }
}
</style>
