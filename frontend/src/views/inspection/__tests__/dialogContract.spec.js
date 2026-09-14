/**
 * 弹窗 v-model 契约静态守卫
 * ========================
 *
 * 钉住 2026-09-14 的缺陷类别：**组件声明了 `modelValue` 却从不读它**。
 *
 * 症状是「点按钮没反应，弹窗不出现」——而且**不报错**，控制台干干净净。
 *
 * 三个文件同时中招（RecordViewer / StatsDialog / PlanDetail），写法一模一样：
 *
 *     const props = defineProps({ modelValue: Boolean, ... })   // 对外承诺可被 v-model 控制
 *     const visible = ref(false)                                // 另起一个局部变量
 *     <el-dialog v-model="visible">                             // 却绑到局部变量上
 *     // props.modelValue 全文件从未出现 → 局部 ref 没有任何路径被置 true
 *
 * 父组件把 `modelValue` 改成 true 只改了 prop，弹窗读的是另一个变量，
 * 于是**永远打不开**；而 `handleClose` 里那句 `visible.value = false`
 * 是唯一的赋值语句，只会让它更假。
 *
 * 为什么单测没抓到：这三个文件此前零覆盖，唯一提到 PlanDetail 的 `Plan.spec.js`
 * 还用 `PlanDetail: true` 把整个组件 stub 掉了。
 *
 * 为什么光加单测不够：三个文件是**同一段代码抄了三遍**。
 * 不把规则钉死，第四个弹窗就会照抄第三遍。
 *
 * ── 规则的边界（写窄了会误报，写宽了会漏报，这里两头都试过）──
 *
 * 1. **前置条件**：只检查在 `defineProps` 里**声明过** `modelValue` 的组件。
 *    页面自有的弹窗（如 `alarm/Center.vue` 绑自己的 `detailVisible`）并不对外承诺
 *    可被 v-model 控制，是合法的。去掉这个前提，守卫会误报 11 个。
 * 2. **绑定判定**：浮层的 `v-model` / `:model-value` 绑的若不是 `modelValue` 本身，
 *    就必须能从 `props.modelValue` 同步过来。
 *    `:model-value="modelValue"` 直绑（`device/ArchiveDetail.vue` 那种）算合规——
 *    漏掉这一条会误报 5 个。
 * 3. 只认 `props.modelValue`、`defineModel()`、解构写法三种同步来源。
 *    ⚠️ 不能退化成「文件里出现 modelValue 字样就算消费」：三个坏文件都有
 *    `defineEmits(['update:modelValue'])`，那个字符串里就含 `modelValue`，
 *    这么写守卫会全绿——**恰好漏掉它本该抓的那三个**。
 * 4. **注释不参与判定**（见 `stripComments`）。这条是实测出来的：回退修复后守卫
 *    没红，才发现它"读"的是修复时顺手写的那句说明注释。
 *
 * ── 本守卫**覆盖不到**的情况（别把它的绿灯当成"弹窗没问题"）──
 *
 * 它是"**声明了却完全没读**"的检查，不做数据流分析。如果组件在某处读了
 * `props.modelValue`（比如加了个 `watch(() => props.modelValue, ...)` 去拉数据），
 * 但浮层的 `v-model` 仍绑在局部 ref 上，**守卫会放行**——而弹窗依然打不开。
 * 实测：把 `RecordViewer` 的 computed 回退成 `ref(false)` 后，
 * 守卫是绿的，是 `RecordViewer.spec.js` 的 T1/T4/T5 把它拦下来的。
 *
 * **结论：组件级的弹窗测试是主力，本守卫只是兜底。** 两个都要有。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')

/** 递归收集所有 .vue 文件 */
function collectVueFiles(dir, acc = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      collectVueFiles(full, acc)
    } else if (entry.endsWith('.vue')) {
      acc.push(full)
    }
  }
  return acc
}

/**
 * 去掉注释（HTML / 块 / 行）后再做判定。
 *
 * ⚠️ **必须去注释**，否则守卫有致命漏报：修复时通常会写一句
 * 「必须是 computed 代理到 `props.modelValue`」的说明，而注释里只要**出现**
 * `props.modelValue` 这个字符串，守卫就认为「该 prop 已被消费」而放行——
 * 于是把修复回退成 `const visible = ref(false)` 之后守卫依然全绿。
 * 这个漏洞是 2026-09-14 做变异测试时实测出来的：回退修复后守卫没红，
 * 才发现它读的是注释而不是代码。
 *
 * 简化处理：不区分字符串字面量里的 `//`（如 URL），代价是可能多切掉几个字符，
 * 对本守卫要找的几个标识符没有影响。
 */
function stripComments(source) {
  return source
    .replace(/<!--[\s\S]*?-->/g, '')   // HTML 注释
    .replace(/\/\*[\s\S]*?\*\//g, '')  // 块注释
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1') // 行注释（避开 https:// 的 `://`）
}

/**
 * 取出 `defineProps(...)` 的实参文本（按括号配对切，避免被嵌套的 `)` 截断）。
 * 返回 null 表示该文件没调用 defineProps。
 */
function definePropsBody(source) {
  const at = source.search(/defineProps\s*[(<]/)
  if (at === -1) return null
  const paren = source.indexOf('(', at)
  if (paren === -1) return null
  let depth = 0
  for (let i = paren; i < source.length; i++) {
    if (source[i] === '(') depth += 1
    else if (source[i] === ')') {
      depth -= 1
      if (depth === 0) return source.slice(paren + 1, i)
    }
  }
  return null
}

/**
 * 判定一个 .vue 是否违反契约。违规返回 `{ tag, bound }`，合规返回 null。
 *
 * 传入的 source 会先被 `stripComments()` 处理，注释不参与判定。
 */
export function findDialogContractViolation(rawSource) {
  const source = stripComments(rawSource)

  // ── 前置条件：只有「对外声明了 modelValue」的组件才受此约束 ──
  const propsBody = definePropsBody(source)
  if (propsBody === null) return null
  const typeArgs = source.match(/defineProps\s*<([\s\S]*?)>\s*\(/)
  const declaresModelValue =
    /\bmodelValue\s*:/.test(propsBody) || (typeArgs !== null && /\bmodelValue\b/.test(typeArgs[1]))
  if (!declaresModelValue) return null

  // ── 找到浮层的 model 绑定 ──
  const m = source.match(/<(el-dialog|el-drawer)\b[^>]*?(?::model-value|v-model)="([^"]+)"/s)
  if (m === null) return null
  const bound = m[2].trim()

  // 直绑 prop 本身：完全正确
  if (bound === 'modelValue') return null

  // 绑到别的变量上：必须能从 props.modelValue 同步过来
  if (/defineModel\s*\(/.test(source)) return null
  if (/props\.modelValue/.test(source)) return null
  if (/const\s*\{[^}]*\bmodelValue\b[^}]*\}\s*=\s*defineProps/.test(source)) return null
  if (/const\s*\{[^}]*\bmodelValue\b[^}]*\}\s*=\s*props\b/.test(source)) return null

  return { tag: m[1], bound }
}

describe('弹窗 v-model 契约（静态守卫）', () => {
  const files = collectVueFiles(SRC)

  it('T1: 扫描范围有效（防止 glob 写错导致守卫空转）', () => {
    // 守卫静默失效比没有守卫更危险：它给的是「已经检查过了」的假安心
    expect(files.length).toBeGreaterThan(30)
    expect(files.some((f) => f.endsWith('ExecutionDialog.vue'))).toBe(true)
  })

  it('T2: 声明了 modelValue 的组件，浮层必须真的绑在它上面', () => {
    const offenders = files
      .map((f) => ({ file: relative(SRC, f), hit: findDialogContractViolation(readFileSync(f, 'utf8')) }))
      .filter((r) => r.hit !== null)
      .map((r) => `${r.file}  <${r.hit.tag} v-model="${r.hit.bound}">`)

    expect(
      offenders,
      '这些组件对外声明了 modelValue，浮层却绑在局部变量上 —— ' +
        '父组件的 v-model 改不动它，弹窗永远打不开（且不报错）'
    ).toEqual([])
  })

  it('T3: 已修好的组件不得误报', () => {
    const read = (rel) => readFileSync(join(SRC, rel), 'utf8')

    // computed 消费 prop（ExecutionDialog 的写法）
    expect(findDialogContractViolation(read('views/inspection/ExecutionDialog.vue'))).toBeNull()
    // watch props.modelValue 手动同步（PlanForm 的写法）
    expect(findDialogContractViolation(read('views/inspection/PlanForm.vue'))).toBeNull()
    // 模板里直绑 :model-value="modelValue"（ArchiveDetail / OrderForm 的写法）
    expect(findDialogContractViolation(read('views/device/ArchiveDetail.vue'))).toBeNull()
    expect(findDialogContractViolation(read('views/repair/OrderForm.vue'))).toBeNull()
    // 页面自有弹窗、未声明 modelValue —— 不受约束
    expect(findDialogContractViolation(read('views/alarm/Center.vue'))).toBeNull()
  })

  it('T4: 守卫能识别出缺陷写法本身（自检，否则正则写错会恒绿）', () => {
    const bad = `
      <template><el-dialog v-model="visible"><div>x</div></el-dialog></template>
      <script setup>
      const props = defineProps({ modelValue: { type: Boolean, default: false } })
      const emit = defineEmits(['update:modelValue'])
      const visible = ref(false)
      function handleClose() { visible.value = false }
      </script>
    `
    const hit = findDialogContractViolation(bad)
    expect(hit, '守卫必须能抓出这个写法的缺陷').not.toBeNull()
    expect(hit.bound).toBe('visible')
  })

  it('T5: 注释里提到 props.modelValue 不算消费（否则守卫会被注释骗过）', () => {
    // 实测教训：修复时顺手写的说明「必须是 computed 代理到 props.modelValue」
    // 会让守卫认为该 prop 已被消费。把修复回退成 ref(false) 后守卫依然全绿——
    // 它读的是注释，不是代码。
    const sneaky = `
      <template><el-dialog v-model="visible"><div>x</div></el-dialog></template>
      <script setup>
      // 这里本来应该是 computed 代理到 props.modelValue，但被回退了
      /* 也不能靠这种块注释：props.modelValue */
      const props = defineProps({ modelValue: { type: Boolean, default: false } })
      const visible = ref(false)
      </script>
    `
    expect(findDialogContractViolation(sneaky), '注释不能算作消费').not.toBeNull()
  })
})
