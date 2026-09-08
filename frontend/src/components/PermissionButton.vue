<template>
  <el-button
    v-permission="permission"
    :type="type"
    :size="size"
    :plain="plain"
    :round="round"
    :circle="circle"
    :loading="loading"
    :disabled="disabled"
    @click="$emit('click', $event)"
  >
    <slot />
  </el-button>
</template>

<script setup>
defineProps({
  permission: { type: [String, Array], required: true },
  type: { type: String, default: 'primary' },
  size: { type: String, default: 'default' },
  plain: { type: Boolean, default: false },
  round: { type: Boolean, default: false },
  circle: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

defineEmits(['click'])
</script>
