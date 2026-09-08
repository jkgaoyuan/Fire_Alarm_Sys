<template>
  <el-aside class="sidebar" width="220px">
    <div class="logo">
      <span class="logo-text">消防监控</span>
    </div>
    <el-scrollbar>
      <el-menu
        :default-active="activeMenu"
        :collapse="false"
        :collapse-transition="false"
        router
        background-color="#1a1a2e"
        text-color="#bfcbd9"
        active-text-color="#c23531"
      >
        <SidebarItem
          v-for="route in menus"
          :key="route.perm_code || route.path"
          :item="route"
        />
      </el-menu>
    </el-scrollbar>
  </el-aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { usePermissionStore } from '@/stores/permission'
import SidebarItem from './SidebarItem.vue'

const route = useRoute()
const permissionStore = usePermissionStore()

const menus = computed(() => permissionStore.menus)
const activeMenu = computed(() => {
  const { meta, path } = route
  if (meta?.activeMenu) return meta.activeMenu
  return path
})
</script>

<style lang="scss" scoped>
.sidebar {
  background: #1a1a2e;
  box-shadow: 2px 0 6px rgba(0, 0, 0, 0.1);

  .logo {
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);

    .logo-text {
      color: #fff;
      font-size: 18px;
      font-weight: 600;
      letter-spacing: 2px;
    }
  }

  :deep(.el-menu) {
    border-right: none;
  }
}
</style>
