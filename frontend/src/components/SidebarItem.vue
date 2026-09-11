<template>
  <div class="sidebar-item">
    <!-- 有子菜单 -->
    <el-sub-menu
      v-if="item.children && item.children.length > 0"
      :index="item.path"
    >
      <template #title>
        <el-icon v-if="item.meta?.icon">
          <component :is="iconMap[item.meta.icon]" />
        </el-icon>
        <span>{{ item.meta?.title }}</span>
      </template>
      <SidebarItem
        v-for="child in item.children"
        :key="child.path || child.name"
        :item="child"
      />
    </el-sub-menu>

    <!-- 无子菜单 - 使用 router.push 直接导航 -->
    <el-menu-item
      v-else
      :index="item.path"
      @click="handleNavigation"
    >
      <el-icon v-if="item.meta?.icon">
        <component :is="iconMap[item.meta.icon]" />
      </el-icon>
      <template #title>
        <span>{{ item.meta?.title }}</span>
      </template>
    </el-menu-item>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

const router = useRouter()

defineProps({
  item: {
    type: Object,
    required: true,
  },
})

// 图标名 → 组件对象的映射（供动态渲染使用）
const iconMap = ElementPlusIconsVue

// 处理导航点击
// IMPORTANT: Use full path with leading slash for Vue Router compatibility
function handleNavigation() {
  const navPath = item.path.startsWith('/') ? item.path : '/' + item.path
  console.log('[SidebarItem] Navigating to:', navPath)
  router.push(navPath)
}
</script>
