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

// ---------------------------------------------------------------------------
// localStorage：Node 22+ 的实验性 Web Storage 会盖掉 jsdom 的实现
//
// 现象：jsdom 环境明明生效（window / document / navigator 都正常、
// environment 就是 'jsdom'），但 `window.localStorage` 是 undefined，
// 读它的代码直接抛 TypeError。启动测试时会看到一条 Node 警告：
//   ExperimentalWarning: localStorage is not available because
//   --localstorage-file was not provided.
//
// 原因：Node 把 localStorage 定义成了 globalThis 上的一个 getter，没有
// --localstorage-file 时返回 undefined；而 vitest 的 jsdom 环境里
// `window === globalThis`，挂属性时 Node 的 getter 就覆盖了 jsdom 的那份。
// sessionStorage 不受影响（Node 的 webstorage 只定义了 localStorage）。
//
// 受影响的是**任何真的去读 token 的测试**：`OrderList.vue` 挂载时调
// `useAuthStore()` → `stores/auth.js` 的 `ref(getToken())` →
// `utils/auth.js` 的 `localStorage.getItem(...)`。表现为整文件 10 条用例
// 全挂，且报错都指向同一行——看着像 10 个 bug，实际是 1 个环境问题。
//
// 这里补一个符合 Web Storage 语义的内存实现。只在缺失时兜底，
// 不覆盖正常的浏览器实现。
// ---------------------------------------------------------------------------
if (typeof globalThis.localStorage === 'undefined') {
  const store = new Map()

  const localStorageShim = {
    getItem(key) {
      const k = String(key)
      return store.has(k) ? store.get(k) : null
    },
    setItem(key, value) {
      // Web Storage 会把 key/value 一律转成字符串
      store.set(String(key), String(value))
    },
    removeItem(key) {
      store.delete(String(key))
    },
    clear() {
      store.clear()
    },
    key(index) {
      return Array.from(store.keys())[index] ?? null
    },
    get length() {
      return store.size
    },
  }

  Object.defineProperty(globalThis, 'localStorage', {
    value: localStorageShim,
    configurable: true,
    writable: true,
  })
}
