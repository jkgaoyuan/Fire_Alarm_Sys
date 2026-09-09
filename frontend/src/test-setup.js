/**
 * Vitest 全局前置：补齐 jsdom 缺失的浏览器 API，使 Element Plus 组件可挂载
 */

// el-table / el-scrollbar 依赖 ResizeObserver 计算布局，jsdom 未实现
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return []
    }
  }
}
