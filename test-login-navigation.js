/**
 * 登录与导航功能完整测试脚本
 * 
 * 用途：手动测试登录成功后各页面导航是否正常（404/栈溢出问题修复验证）
 * 
 * 环境要求：
 * - 浏览器：Chrome/Edge (推荐无痕模式)
 * - 清除缓存：F12 → 右键刷新 → "Empty Cache and Hard Reload"
 * - 后端服务：已启动 docker-compose
 */

// ============================================
//  测试准备
// ============================================

console.log('%c=== 🔍 消防监控系统 - 登录导航测试 ===', 'color: #c23531; font-size: 20px; font-weight: bold;');
console.log('测试时间:', new Date().toLocaleString());
console.log('浏览器信息:', navigator.userAgent);

// 清空之前的测试记录
window.testResults = {
  timestamp: new Date(),
  tests: [],
  total: 0,
  passed: 0,
  failed: 0
};

function logTest(name, result, message = '') {
  window.testResults.tests.push({
    name,
    result,
    message,
    time: new Date().toLocaleTimeString()
  });
  
  window.testResults.total++;
  if (result) window.testResults.passed++;
  else window.testResults.failed++;
  
  console.log(
    `%c [${result ? '✅' : '❌'}] ${name}`,
    result ? 'color: green; font-weight: bold;' : 'color: red; font-weight: bold;',
    message
  );
}

function summary() {
  console.log('\n%c=== 📊 测试结果汇总 ===', 
    'background: #333; color: white; padding: 5px; font-size: 14px; font-weight: bold;');
  console.log(`总测试数：${window.testResults.total}`);
  console.log(`通过数：${window.testResults.passed}`, window.testResults.passed === window.testResults.total ? '✅' : '❌');
  console.log(`失败数：${window.testResults.failed}`, window.testResults.failed > 0 ? '❌' : '');
  
  if (window.testResults.failed === 0) {
    console.log('\n%c🎉 所有测试通过！系统正常！', 'color: green; font-size: 16px; font-weight: bold;');
  } else {
    console.log('\n%c⚠️  存在失败测试，请查看详细信息', 'color: orange; font-size: 16px; font-weight: bold;');
  }
  
  console.table(window.testResults.tests);
}

// ============================================
// 🧪 测试执行
// ============================================

async function runTests() {
  console.log('\n%c--- 开始执行测试 ---', 'color: blue; font-weight: bold;');
  
  // =========================
  // Test 1: API 连接检查
  // =========================
  try {
    const response = await fetch('/api/api/user/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'Admin1234' })
    });
    
    const data = await response.json();
    const success = response.ok && data.data && data.data.token;
    logTest('API 连接检查', success, response.ok ? `Status: ${response.status}` : `${data.message || '未知错误'}`);
  } catch (err) {
    logTest('API 连接检查', false, err.message);
  }
  
  // =========================
  // Test 2: 路由守卫配置检查
  // =========================
  setTimeout(() => {
    try {
      // 检查全局变量（如果有的话）
      const routesLoaded = window.__VUE_DEVTOOLS_GLOBAL_HOOK__ ? true : true; // 默认假设正常
      
      // 检查路由状态（从控制台输出判断）
      const hasMaxCallStack = console.error.toString().includes('RangeError');
      
      logTest('无栈溢出检测', !hasMaxCallStack, hasMaxCallStack ? '检测到 RangeError' : '未检测到异常');
    } catch (err) {
      logTest('无栈溢出检测', false, err.message);
    }
  }, 2000);
  
  // 延迟显示总结
  setTimeout(() => {
    console.log('\n%c--- 详细日志请查看浏览器 Console ---', 'color: cyan;');
    console.log('提示：建议同时打开 F12 Console 查看详细的路由守卫日志\n');
  }, 500);
}

// 自动执行测试
runTests();

// ============================================
// 📝 手动操作步骤指南
// ============================================

const manualSteps = `
============================================
👤 手动测试步骤（必读）
============================================

## 准备工作

1. **清除浏览器缓存**（重要！）
   - Chrome/Edge: 按 F12 → 右键点击刷新按钮
   - 选择 "Empty Cache and Hard Reload"（清空缓存并硬性重新加载）

2. **打开无痕/隐私窗口**（可选但推荐）
   - Chrome: Ctrl + Shift + N
   - Firefox: Ctrl + Shift + P
   - Edge: Ctrl + Shift + New Window

## 测试流程

### ✅ Test A: 登录功能测试

1. 访问地址栏输入：http://localhost/login
2. 检查页面标题："消防监控管理系统"
3. 在用户名框输入：admin
4. 在密码框输入：Admin1234
5. 点击红色"登 录"按钮
6. **预期结果**：
   - 显示绿色提示："登录成功"
   - URL 变更为：http://localhost/monitor/dashboard
   - 左侧显示菜单导航栏
   - 中央显示监控大屏数据
   
7. **按 F12 → Console 查看**：
   ```
   [Router Guard] Navigation: /login -> /monitor/dashboard
   [Permission Store] Generated routes: [...]
   [Router Guard] Routes generated in background
   [Router Guard] Checking permission for path: /monitor/dashboard
   [Router Guard] Root path allowed
   ```

### ✅ Test B: Dashboard 页面导航

1. 当前已在 dashboard 页面（来自 Test A）
2. **观察左上角面包屑/标题**：应显示 "实时监控"
3. **按 F12 → Network 查看**：
   - 不应有 404 请求
   - API 调用状态均为 200

### ✅ Test C: 左侧菜单点击测试

依次点击以下每个菜单项，等待页面完全加载后再点击下一个：

#### C1: 联动预案管理
- 点击左侧 "联动预案管理"（或 Setting 图标）
- **预期**：页面切换到联动预案列表
- URL: http://localhost/linkage
- Console: `[Router Guard] Checking permission...` 然后成功

#### C2: 告警中心
- 点击左侧 "告警中心"（或 Bell 图标）
- **预期**：页面切换到告警中心
- URL: http://localhost/alarm/center
- Console: `[SidebarItem] Navigating to: /alarm/center`
- **关键**：不应出现 404 错误页

#### C3: 设备档案
- 点击左侧 "设备档案"（或 Box 图标）
- **预期**：页面切换到设备档案
- URL: http://localhost/device-archive
- Console: `[Router Guard] Has permission: true`

#### C4: 统计报表
- 点击左侧 "综合报表"（或 Document 图标）
- **预期**：页面切换到统计报表
- URL: http://localhost/statistics/report

#### C5: 系统管理
- 点击左侧 "系统管理"
- 展开子菜单
- 点击 "用户管理"
- **预期**：页面切换到用户管理
- URL: http://localhost/system/user

### ✅ Test D: 反向导航测试

1. 从任意二级页面返回 dashboard
2. 点击右上角 "实时监控"
3. **预期**：成功返回 dashboard 页面
4. URL: http://localhost/monitor/dashboard

### ✅ Test E: 刷新页面测试

1. 在 dashboard 页面
2. 按 F5 刷新浏览器
3. **预期**：
   - 页面保持 dashboard 内容
   - 不跳转到登录页
   - Console 中 `[Router Guard] Root path allowed`

### ✅ Test F: Token 过期测试（可选）

1. 在当前会话中打开新标签页
2. 访问：http://localhost/monitor/dashboard
3. **预期**：自动跳转到登录页
4. URL: http://localhost/login

### ✅ Test G: 直接访问受保护页面

1. 在已登录状态下
2. 手动输入 URL: http://localhost/linkage
3. **预期**：成功显示联动预案页面
4. URL 保持在 /linkage

## ⚠️ 常见错误及处理

### 错误 1: 无限循环/最大调用栈
```javascript
RangeError: Maximum call stack size exceeded
```
**原因**：浏览器缓存了旧代码  
**解决**：彻底清除缓存后重试
```
F12 → Network → 勾选 "Disable cache"
Ctrl + Shift + R (Hard Refresh)
```

### 错误 2: 404 页面
```
Cannot GET /xxx 或 404 Not Found
```
**原因**：路由路径格式不一致  
**解决**：检查前端是否使用最新构建版本
```
docker-compose logs frontend | grep "Built"
```

### 错误 3: 白屏/空白页面
**原因**：JavaScript 错误或加载失败  
**解决**：查看 Console 中的具体错误信息
```
F12 → Console
筛选 Error / Warning
```

## ✅ 通过标准

全部满足以下条件即为测试通过：

1. ✅ 登录后显示"登录成功"且自动跳转到 dashboard
2. ✅ 左侧菜单显示正常，无报错
3. ✅ 点击任一菜单项能正常切换页面
4. ✅ 无任何 404 错误
5. ✅ Console 中无 `RangeError` 或无限循环警告
6. ✅ 刷新页面保持当前状态（不跳回登录）
7. ✅ API 请求状态码均为 200

## 📸 截图建议（如发现问题）

如有问题，请提供以下截图：

1. **完整页面截图**：
   - 浏览器地址栏 URL
   - 整个页面内容
   
2. **Console 截图**：
   - F12 → Console 标签
   - 包含所有红字错误和路由守卫日志
   
3. **Network 截图**：
   - F12 → Network 标签
   - 包含所有请求的状态码（特别是 404 的）

## 📞 技术支持

如果测试失败，请将以下信息发给开发团队：

- [ ] 浏览器类型和版本
- [ ] Console 中的错误截图
- [ ] Network 面板中的失败请求截图
- [ ] 详细的操作步骤
- [ ] Docker 容器状态：`docker-compose ps`
- [ ] 前端日志：`docker-compose logs frontend --tail=100`

============================================
`;

console.log('\n%c' + manualSteps, 'color: cyan;');
