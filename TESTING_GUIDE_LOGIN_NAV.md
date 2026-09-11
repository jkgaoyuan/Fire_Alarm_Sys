# 🔍 登录与导航功能测试 - 完整测试指南

## 🎯 测试目标
验证登录后各页面导航是否正常工作（无 404/栈溢出问题）

---

## 📋 快速测试清单（5 分钟完成）

### ✅ 必做基础测试

| # | 测试项 | 操作步骤 | 预期结果 | 状态 |
|---|--------|----------|----------|------|
| 1 | **清除缓存** | F12 → 右键刷新 → "Empty Cache and Hard Reload" | 确认缓存已清空 | ☐ |
| 2 | **登录** | http://localhost/login<br>用户名: admin<br>密码: Admin1234 | 显示"登录成功"<br>跳转到 /monitor/dashboard | ☐ |
| 3 | **Dashboard 正常** | 查看监控大屏页面 | 显示数据图表<br>左侧菜单可见 | ☐ |
| 4 | **点击告警中心** | 点击左侧 "告警中心" | 页面切换成功<br>URL 变为 /alarm/center | ☐ |
| 5 | **点击设备档案** | 点击左侧 "设备档案" | 页面切换成功<br>无 404 错误 | ☐ |
| 6 | **点击联动预案** | 点击左侧 "联动预案管理" | 页面切换成功<br>无栈溢出错误 | ☐ |
| 7 | **统计报表** | 点击左侧 "综合报表" | 页面切换成功 | ☐ |
| 8 | **返回 Dashboard** | 点击右上角标题或系统管理 | 返回监控大屏 | ☐ |
| 9 | **页面刷新** | 按 F5 刷新 | 保持当前页面<br>不跳回登录 | ☐ |
| 10 | **Console 检查** | F12 → Console | 无 RangeError<br>所有路由守卫日志正常 | ☐ |

---

## 🧪 详细测试步骤

### 第 1 步：准备工作

```bash
# 确保服务已启动
cd e:\pycharm\AI_PROJECT_CODE\Fire_Alarm_Sys
docker-compose ps

# 应该看到以下服务运行中：
# NAME                  STATUS
# fire_alarm_frontend   Up (healthy)
# fire_alarm_backend    Up (healthy)
# fire_alarm_postgres   Up (healthy)
# fire_alarm_redis      Up (healthy)
```

### 第 2 步：清除浏览器缓存（至关重要！）

**Chrome/Edge 操作方法：**

1. 按 `F12` 打开开发者工具
2. 右键点击浏览器地址栏右侧的刷新按钮 (↻)
3. 在弹出菜单中选择 **"Empty Cache and Hard Reload"** (清空缓存并硬性重新加载)
4. 关闭所有相关标签页
5. 新建一个标签页

**或使用无痕模式：**
- Windows: `Ctrl + Shift + N`
- Mac: `Cmd + Shift + N`

### 第 3 步：执行登录测试

#### 3.1 访问登录页面
```
地址栏输入：http://localhost/login
按 Enter 键
```

**预期表现：**
- ✅ 页面显示"消防监控管理系统"标题
- ✅ 显示登录表单（用户名和密码输入框）
- ✅ 红色"登 录"按钮可见

#### 3.2 执行登录
```
用户名：admin
密码：Admin1234
点击"登 录"按钮
```

**预期表现（关键指标）：**
- ✅ 显示绿色提示消息："登录成功"
- ✅ URL 自动变更为：`http://localhost/monitor/dashboard`
- ✅ 页面切换到监控大屏
- ✅ 左侧显示导航菜单（实时监控、联动预案管理、告警中心等）
- ✅ 中央区域显示监控数据图表

#### 3.3 检查 Console 日志
按 `F12` 打开 Console，应该看到类似以下输出：

```javascript
// ✅ 成功的日志示例
[Router Guard] Navigation: /login -> /
[Router Guard] Whitelisted path: /login
[Router Guard] Routes not loaded, fetching menus...
[Permission Store] Generated routes: ['/monitor/dashboard (Dashboard)', '/alarm/center (AlarmCenter)', ...]
[Permission Store] Adding 18 dynamic routes
[Permission Store] Added dynamic route: /monitor/dashboard
[Permission Store] Added dynamic route: /alarm/center
[Permission Store] All routes after generation: [...]
[Router Guard] Routes generated in background
[Router Guard] Checking permission for path: /
[Router Guard] Root path allowed
```

**❌ 失败的标志：**
- `RangeError: Maximum call stack size exceeded` ← 栈溢出（说明有无限循环）
- `Cannot find matched route` ← 路由未找到
- `[Router Guard] Has permission: false` ← 权限检查失败

---

### 第 4 步：左侧菜单导航测试

从 Dashboard 页面开始，**依次点击**每个左侧菜单项。

**⚠️ 重要注意事项：**
- 每次点击后等待页面完全加载（通常 1-2 秒）
- 观察 URL 变化
- 检查 Console 中的路由守卫日志
- **绝对不应出现 404 错误或空白页**

#### 菜单项列表及预期结果：

| 序号 | 菜单名称 | 图标 | 预期 URL | Console 关键词 |
|------|----------|------|----------|----------------|
| 1 | 实时监控 | Monitor | `/monitor/dashboard` | ✅ 当前页 |
| 2 | 联动预案管理 | Setting | `/linkage` | `Checking permission... Has permission: true` |
| 3 | 告警中心 | Bell | `/alarm/center` | `Navigating to: alarm/center` |
| 4 | 设备档案 | Box | `/device-archive` | No 404 error |
| 5 | 巡检计划 | List | `/inspection-plan` | Route added successfully |
| 6 | 巡检任务 | Clipboard | `/inspection-task` | |
| 7 | 消防演练 | VideoCamera | `/drill-event` | |
| 8 | 应急处置 | Sos | `/emergency` | |
| 9 | 维修工单 | Tools | `/repair-order` | |
| 10 | 综合报表 | Document | `/statistics/report` | |
| 11 | 告警趋势 | TrendingUp | `/statistics/alarm-trend` | |
| 12 | 设备状态 | DataAnalysis | `/statistics/device-status` | |
| 13 | 用户管理 | User | `/system/user` | |
| 14 | 角色管理 | Lock | `/system/role` | |
| 15 | 登录日志 | View | `/system/login-log` | |

**点击后的预期行为：**
1. URL 正确变更
2. 页面内容切换
3. 左侧菜单高亮显示当前选项
4. Console 中显示路由守卫日志
5. **无 404 错误**
6. **无栈溢出错误**

---

### 第 5 步：反向导航测试

#### 5.1 使用面包屑导航返回
1. 在任意子页面（如告警中心）
2. 点击右上角的导航文字（如 "实时..."）
3. 应返回 dashboard

#### 5.2 手动输入 URL 测试
1. 在地址栏直接输入：`http://localhost/alarm/center`
2. 按 Enter
3. 应直接进入告警中心页面
4. URL 保持不变

---

### 第 6 步：刷新页面测试

#### 6.1 当前页面刷新
1. 在 dashboard 页面
2. 按 `F5` 或点击浏览器刷新按钮
3. **预期**：保持 dashboard 页面，数据重新加载

#### 6.2 硬刷新
1. 按 `Ctrl + F5`
2. **预期**：页面完全刷新，但仍保持在 dashboard
3. Console 中应没有路由守卫的重载日志

---

### 第 7 步：Console 深度检查

打开 Console (`F12`)，筛选以下内容：

#### ✅ 正常的日志模式
```javascript
// 登录时
[Router Guard] Navigation: /login -> /
[Router Guard] Routes not loaded, fetching menus...
[Permission Store] Generated routes: [Array(18)]
[Router Guard] Routes generated in background

// 点击菜单时
[Router Guard] Checking permission for path: /alarm/center
[Router Guard] Check path: /alarm/center
[Router Guard] Has permission: true
[Router Guard] Permission granted
```

#### ❌ 异常日志模式
```javascript
// ❌ 栈溢出
RangeError: Maximum call stack size exceeded
at Array.forEach (<anonymous>)
// 多次重复函数调用

// ❌ 404 错误
Cannot GET /xxx
RouteNotFound

// ❌ 权限错误
Has permission: false
Redirecting to /403
```

---

## 🐛 常见问题处理

### 问题 1: 无限循环 / 最大调用栈

**现象：**
```
RangeError: Maximum call stack size exceeded
```

**原因：**
- 浏览器缓存了旧版本的前端代码
- 路由守卫逻辑陷入死循环

**解决方法：**
```bash
# 1. 强制清除 Docker 镜像缓存
cd e:\pycharm\AI_PROJECT_CODE\Fire_Alarm_Sys
docker-compose build --no-cache frontend
docker-compose up -d frontend

# 2. 浏览器操作
# - F12 → Network → 勾选 "Disable cache"
# - Ctrl + Shift + R (Hard Refresh)
# - 关闭所有标签页
# - 新建窗口重新访问
```

### 问题 2: 404 Not Found

**现象：**
- 点击菜单显示 404 页面
- 或 URL 变成 404

**可能原因：**
- 动态路由未正确添加
- 路径格式不一致（缺少前导斜杠）

**调试方法：**
```javascript
// 在 Console 中检查
console.log('当前路由:', router.getRoutes().map(r => r.path))
// 应包含所有菜单项路径
```

**检查点：**
1. 后端返回的菜单数据是否正确？
2. 前端是否生成了所有动态路由？
3. 路由守卫是否正常放行？

### 问题 3: 白屏/空白页面

**可能原因：**
- JavaScript 加载失败
- Vue Router 配置错误
- CSS 样式冲突

**调试方法：**
```bash
# 查看前端日志
docker-compose logs frontend --tail=100

# 查看网络请求
F12 → Network → 筛选 JS/CSS
# 所有资源应为 200 OK
```

### 问题 4: 登录后仍停留在登录页

**原因：**
- Token 未正确保存
- `generateRoutes()` 执行失败

**解决方法：**
```javascript
// 检查 localStorage
console.log(localStorage.getItem('token'))

// 重新登录
// 确保密码大小写正确：Admin1234
```

---

## 📊 测试结果汇总

请在完成测试后填写：

### 基本信息
- [ ] 测试时间：__________
- [ ] 浏览器：Chrome / Edge / Firefox ________ 版本：_______
- [ ] 操作系统：Windows 10/11 / Mac OS / Linux
- [ ] 是否使用无痕模式：是 / 否

### 测试结果
| 测试项目 | 通过 | 失败 | 备注 |
|----------|------|------|------|
| 1. 登录功能 | ☐ | ☐ | |
| 2. Dashboard 显示 | ☐ | ☐ | |
| 3. 菜单导航（全部） | ☐ | ☐ | 共 _ 个菜单项 |
| 4. 反向导航 | ☐ | ☐ | |
| 5. 页面刷新 | ☐ | ☐ | |
| 6. Console 日志 | ☐ | ☐ | 有无异常 |

### 发现的问题
- [ ] 无任何问题（✅）
- [ ] 存在以下问题（详细说明）：
  ```
  问题 1: _______________________
  问题 2: _______________________
  问题 3: _______________________
  ```

### 截图证据（如有问题）
- [ ] 控制台错误截图
- [ ] Network 面板截图
- [ ] 问题页面截图

---

## 📞 提交问题报告

如果发现问题，请提供以下信息：

### 必需信息
1. **浏览器 Console 截图**
   - 包含所有红字错误
   - 路由守卫日志
   - 时间戳

2. **Network 面板截图**
   - 显示所有请求的状态码
   - 特别是 404 的请求

3. **问题页面截图**
   - 完整浏览器窗口
   - 包含地址栏 URL

4. **Docker 容器状态**
   ```bash
   docker-compose ps
   
   # 输出示例
   NAME                  STATUS
   fire_alarm_frontend   Up (healthy)
   fire_alarm_backend    Up (healthy)
   ```

5. **前端日志（最近 100 行）**
   ```bash
   docker-compose logs frontend --tail=100
   ```

### 联系开发团队
将上述信息发送给开发团队，或在项目中提交 Issue。

---

## ✅ 测试通过标准

所有以下条件必须满足：

1. ✅ 能成功登录并进入 dashboard
2. ✅ 左侧菜单所有项都能正常点击
3. ✅ 点击后正确切换到对应页面
4. ✅ 没有任何 404 错误
5. ✅ Console 中没有 `RangeError` 或栈溢出警告
6. ✅ 刷新页面保持当前状态
7. ✅ API 请求成功率 100%（无 500/404）

---

## 📝 测试记录

### 第一轮测试
- 测试人员：__________
- 测试日期：__________
- 测试结果：☐ 通过 ☐ 部分通过 ☐ 失败
- 备注：_________________________________

### 第二轮测试（修复后）
- 测试人员：__________
- 测试日期：__________
- 测试结果：☐ 通过 ☐ 部分通过 ☐ 失败
- 备注：_________________________________

---

**祝您测试顺利！🎯**

如有任何问题，请参考本指南的"常见问题处理"章节或联系开发团队。
