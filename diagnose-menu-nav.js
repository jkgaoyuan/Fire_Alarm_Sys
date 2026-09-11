/**
 * Diagnostic Tool for Menu Navigation Issue
 * 
 * Usage: Open browser console (F12) while logged in, then paste this code
 * It will show all registered routes and test navigation manually
 */

(function diagnoseMenuNavigation() {
  console.log('%c=== MENU NAVIGATION DIAGNOSTIC TOOL ===', 'color: blue; font-size: 16px; font-weight: bold');
  
  // Get Vue Router instance from global variables
  const router = window.__VUE_DEVTOOLS_GLOBAL_HOOK__ ? null : null;
  
  try {
    // Check if we can access router from permission store
    const permStore = document.querySelector('[pinia]') ? 
      (window.permissionStore || null) : null;
    
    console.log('🔍 Checking available data...');
    
    // List all routes in Vue Router
    console.log('📋 Registered Routes:');
    const allRoutes = router.getRoutes();
    allRoutes.forEach(route => {
      console.log(`   ${route.path} [${route.name}]`);
      if (route.children && route.children.length > 0) {
        route.children.forEach(child => {
          console.log(`      └─ ${child.path} [${child.name}]`);
        });
      }
    });
    
    // Test specific paths
    console.log('\n🧪 Testing Navigation Paths:');
    const testPaths = [
      'monitor/dashboard',
      'alarm/center', 
      'device/archive',
      'linkage/plan',
      '/monitor/dashboard',
      '/alarm/center'
    ];
    
    testPaths.forEach(path => {
      try {
        const matched = router.hasRoute(path);
        console.log(`   ${path.padEnd(20)} → ${matched ? '✅ EXISTS' : '❌ NOT FOUND'}`);
      } catch (e) {
        console.log(`   ${path.padEnd(20)} → Error: ${e.message}`);
      }
    });
    
    // Check menu items
    console.log('\n📡 Menu Display Data:');
    const menuItems = Array.from(document.querySelectorAll('.el-menu-item'));
    if (menuItems.length > 0) {
      console.log(`   Found ${menuItems.length} menu items`);
      menuItems.slice(0, 5).forEach(item => {
        const text = item.textContent.trim().replace(/\s+/g, ' ');
        const index = item.getAttribute('index');
        console.log(`   - "${text}" (index: ${index})`);
      });
    } else {
      console.log('   No el-menu-item elements found');
    }
    
    // Provide interactive navigation testing
    console.log('\n⌨️  Interactive Testing:');
    console.log('   Type "test-path <path>" to test a specific route');
    console.log('   Example: test-path alarm/center');
    
    // Set up command listener
    window.testMenuNav = function(path) {
      const normalizedPath = path.startsWith('/') ? path.substring(1) : path;
      console.log(`\n--- Testing: ${normalizedPath} ---`);
      console.log(`Normalizing: ${path} → ${normalizedPath}`);
      
      const exists = router.hasRoute(normalizedPath);
      console.log(`Route exists: ${exists ? 'YES ✅' : 'NO ❌'}`);
      
      if (exists) {
        try {
          router.push(normalizedPath).then(() => {
            console.log(`Navigation successful! Current path: ${router.currentRoute.value.path}`);
          }).catch(err => {
            console.error('Navigation failed:', err.message);
          });
        } catch (e) {
          console.error('Push error:', e.message);
        }
      } else {
        console.log('Trying alternative matches...');
        allRoutes.forEach(route => {
          if (route.path.includes(normalizedPath.split('/')[0])) {
            console.log(`   Matching candidate: ${route.path}`);
          }
        });
      }
    };
    
    console.log('\n✅ Diagnostic complete. Review the output above.');
    console.log('💡 TIP: Use "test-path <path>" to test navigation manually');
    
  } catch (error) {
    console.error('❌ Diagnostic tool error:', error);
    console.log('Make sure you are on a page where Vue Router is active');
  }
})();
