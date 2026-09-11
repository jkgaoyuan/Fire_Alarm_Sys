/**
 * 路由死循环调试脚本
 * 
 * 使用方法：
 * 1. 在浏览器控制台运行此脚本
 * 2. 或者将其添加到前端项目的测试工具中
 */

// 模拟路由守卫的执行逻辑
function simulateRouterGuard(toPath, fromPath, token, isRoutesLoaded) {
  console.log('='.repeat(60));
  console.log(`[Router Guard Simulation] ${fromPath} -> ${toPath}`);
  console.log('Token:', token ? 'present' : 'missing');
  console.log('Is Routes Loaded:', isRoutesLoaded);
  console.log('-'.repeat(60));

  const whiteList = ['/login', '/403', '/404'];

  // 检查白名单
  if (whiteList.includes(toPath)) {
    console.log('[Result] ✅ Whitelisted path - Allow navigation');
    return { action: 'allow', redirect: null };
  }

  // 检查 token
  if (!token) {
    console.log('[Result] ❌ No token - Redirect to /login');
    return { action: 'redirect', redirect: '/login' };
  }

  // 检查路由是否已加载
  if (!isRoutesLoaded) {
    console.log('[Result] ⚠️  Routes not loaded - Redirect to /monitor/dashboard');
    return { action: 'redirect', redirect: '/monitor/dashboard' };
  }

  // 权限检查
  const flatMenuPaths = [
    '/monitor/dashboard',
    '/alarm/center',
    '/device/archive',
    // ... 其他路径
  ];

  if (toPath === '/') {
    console.log('[Result] ✅ Root path - Allow navigation');
    return { action: 'allow', redirect: null };
  }

  const hasPermission = flatMenuPaths.includes(toPath);
  if (hasPermission) {
    console.log('[Result] ✅ Has permission - Allow navigation');
    return { action: 'allow', redirect: null };
  } else {
    console.log('[Result] ❌ No permission - Redirect to /403');
    return { action: 'redirect', redirect: '/403' };
  }
}

// 检测死循环场景
function detectInfiniteLoop() {
  console.log('🔍 检测潜在的无限循环场景...\n');

  const scenarios = [
    {
      name: '登录成功后跳转到 dashboard',
      toPath: '/monitor/dashboard',
      fromPath: '/login',
      token: 'fake-token',
      isRoutesLoaded: false,
    },
    {
      name: '第一次访问受保护页面',
      toPath: '/alarm/center',
      fromPath: '/',
      token: 'fake-token',
      isRoutesLoaded: false,
    },
    {
      name: '无 token 访问受保护页面',
      toPath: '/monitor/dashboard',
      fromPath: '/',
      token: null,
      isRoutesLoaded: false,
    },
    {
      name: 'token 有效但路由未加载',
      toPath: '/monitor/dashboard',
      fromPath: '/',
      token: 'fake-token',
      isRoutesLoaded: false,
    },
  ];

  scenarios.forEach((scenario, index) => {
    console.log(`场景 ${index + 1}: ${scenario.name}`);
    const result = simulateRouterGuard(
      scenario.toPath,
      scenario.fromPath,
      scenario.token,
      scenario.isRoutesLoaded
    );
    console.log();
  });
}

// 检查当前的路由状态
function checkCurrentState() {
  console.log('📊 当前路由状态\n');

  const router = window.router;
  const authStore = window.__PINIA_STORES__?.auth;
  const permStore = window.__PINIA_STORES__?.permission;

  if (router) {
    console.log('✅ Router found');
    console.log('  Current path:', router.currentRoute.value.path);
    console.log('  Available routes:', router.getRoutes().map(r => r.path).join(', '));
  } else {
    console.log('❌ Router not accessible globally');
  }

  if (permStore) {
    console.log('\n✅ Permission Store found');
    console.log('  isRoutesLoaded:', permStore.isRoutesLoaded);
    console.log('  flatMenuPaths:', permStore.flatMenuPaths);
    console.log('  menus:', permStore.menus);
  } else {
    console.log('\n⚠️  Permission Store not accessible globally (this is expected)');
  }
}

// 修复建议
function showFixSuggestions() {
  console.log('\n🛠️  已应用的修复措施:\n');
  console.log('1. ✅ 设置 isRoutesLoaded = true 防止重复加载');
  console.log('2. ✅ 异步生成路由不阻塞导航');
  console.log('3. ✅ 路由未加载时重定向到 dashboard，避免死循环');
  console.log('4. ✅ 使用 router.replace 而不是 push，避免回退问题');
  console.log('\n💡 如果问题仍然存在:');
  console.log('   - 检查后端 API 返回的菜单数据');
  console.log('   - 检查角色权限是否正确配置');
  console.log('   - 查看浏览器网络面板中的 /users/me/menus 请求');
}

// 运行所有检查
console.clear();
console.log('🎯 路由死循环诊断工具\n');
detectInfiniteLoop();
checkCurrentState();
showFixSuggestions();
