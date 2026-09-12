<template>
  <el-breadcrumb separator="/" class="app-breadcrumb">
    <el-breadcrumb-item
      v-for="(item, index) in breadcrumbs"
      :key="item.path"
    >
      <span
        v-if="index === breadcrumbs.length - 1"
        class="no-redirect"
      >{{ item.title }}</span>
      <a v-else @click.prevent="handleLink(item)">{{ item.title }}</a>
    </el-breadcrumb-item>
  </el-breadcrumb>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const breadcrumbs = ref([])

function getBreadcrumb() {
  const matched = route.matched.filter(item => item.meta && item.meta.title)

  // 如果当前不是首页，在开头加上首页
  const first = matched[0]
  if (!first || first.path !== '/') {
    matched.unshift({
      path: '/',
      meta: { title: '首页' },
    })
  }

  breadcrumbs.value = matched.map(item => ({
    title: item.meta.title,
    path: item.path,
  }))
}

function handleLink(item) {
  router.push(item.path)
}

watch(
  () => route.path,
  () => getBreadcrumb(),
  { immediate: true }
)
</script>

<style lang="scss" scoped>
.app-breadcrumb {
  font-size: 14px;

  .no-redirect {
    color: #97a8be;
    cursor: text;
  }

  a {
    color: #606266;
    text-decoration: none;
    cursor: pointer;

    &:hover {
      color: #c23531;
    }
  }
}
</style>
