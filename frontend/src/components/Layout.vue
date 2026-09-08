<template>
  <el-container class="layout-container">
    <AppSidebar />
    <el-container class="main-container">
      <AppHeader />
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import AppSidebar from '@/components/AppSidebar.vue'
import AppHeader from '@/components/AppHeader.vue'
</script>

<style lang="scss" scoped>
.layout-container {
  height: 100vh;
}

.main-container {
  flex-direction: column;
}

.main-content {
  background: #f5f7fa;
  padding: 20px;
  overflow-y: auto;
}
</style>
