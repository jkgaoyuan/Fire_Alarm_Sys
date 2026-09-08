import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SidebarItem from '../SidebarItem.vue'

// 真实后端返回的菜单数据结构（来自 /users/me/menus）
const backendLeafMenu = {
  path: '/monitor/dashboard',
  name: 'monitor:dashboard',
  meta: { title: '监控大屏', icon: 'Monitor' },
}

const backendParentMenu = {
  path: '/system',
  name: 'system:management',
  meta: { title: '系统管理', icon: 'Setting' },
  children: [
    {
      path: '/system/user',
      name: 'system:user',
      meta: { title: '用户管理', icon: 'User' },
    },
    {
      path: '/system/role',
      name: 'system:role',
      meta: { title: '角色管理', icon: 'UserFilled' },
    },
  ],
}

// 带 slot 渲染的 stub 组件，使 wrapper.text() 能捕获 slot 内容
const stubs = {
  'el-sub-menu': {
    template: '<div class="el-sub-menu-stub"><slot name="title" /><slot /></div>',
  },
  'el-menu-item': {
    template: '<div class="el-menu-item-stub"><slot name="title" /><slot /></div>',
  },
  'el-icon': {
    template: '<span class="el-icon-stub"><slot /></span>',
  },
}

describe('SidebarItem.vue', () => {
  it('应正确渲染叶子菜单项的标题（真实后端数据结构）', () => {
    const wrapper = mount(SidebarItem, {
      props: { item: backendLeafMenu },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('监控大屏')
  })

  it('应递归渲染带子菜单的父菜单', () => {
    const wrapper = mount(SidebarItem, {
      props: { item: backendParentMenu },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('系统管理')
    expect(wrapper.text()).toContain('用户管理')
    expect(wrapper.text()).toContain('角色管理')
  })

  it('无子菜单时应渲染为 el-menu-item', () => {
    const wrapper = mount(SidebarItem, {
      props: { item: backendLeafMenu },
      global: { stubs },
    })
    expect(wrapper.findAll('.el-menu-item-stub')).toHaveLength(1)
    expect(wrapper.findAll('.el-sub-menu-stub')).toHaveLength(0)
  })

  it('有子菜单时应渲染为 el-sub-menu', () => {
    const wrapper = mount(SidebarItem, {
      props: { item: backendParentMenu },
      global: { stubs },
    })
    expect(wrapper.findAll('.el-sub-menu-stub')).toHaveLength(1)
    // 子菜单项应渲染为 el-menu-item
    expect(wrapper.findAll('.el-menu-item-stub')).toHaveLength(2)
  })

  it('无 icon 时不应渲染 el-icon', () => {
    const item = { path: '/a', name: 'a', meta: { title: '无图标' } }
    const wrapper = mount(SidebarItem, {
      props: { item },
      global: { stubs },
    })
    expect(wrapper.findAll('.el-icon-stub')).toHaveLength(0)
  })

  it('有 icon 时应渲染 el-icon', () => {
    const wrapper = mount(SidebarItem, {
      props: { item: backendLeafMenu },
      global: { stubs },
    })
    expect(wrapper.findAll('.el-icon-stub')).toHaveLength(1)
  })

  it('应使用 path 作为 index', () => {
    const wrapper = mount(SidebarItem, {
      props: { item: backendLeafMenu },
      global: { stubs },
    })
    const menuItem = wrapper.find('.el-menu-item-stub')
    expect(menuItem.attributes('index')).toBe('/monitor/dashboard')
  })
})
