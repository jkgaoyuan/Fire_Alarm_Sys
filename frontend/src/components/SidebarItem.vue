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

    <!-- 无子菜单 -->
    <el-menu-item v-else :index="item.path">
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
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

defineProps({
  item: {
    type: Object,
    required: true,
  },
})

// 图标名 → 组件对象的映射（供动态渲染使用）
const iconMap = ElementPlusIconsVue
</script>
