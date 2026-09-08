import { describe, it, expect } from 'vitest'
import request from '../request'

describe('request.js', () => {
  it('应导出 axios 实例', () => {
    expect(typeof request.get).toBe('function')
    expect(typeof request.post).toBe('function')
    expect(typeof request.put).toBe('function')
    expect(typeof request.delete).toBe('function')
  })

  it('实例应具有正确的超时设置', () => {
    expect(request.defaults.timeout).toBe(30000)
  })

  it('实例应具有 Content-Type header', () => {
    expect(request.defaults.headers['Content-Type']).toBe('application/json')
  })

  it('应注册了请求拦截器', () => {
    expect(request.interceptors.request.handlers.length).toBeGreaterThan(0)
  })

  it('应注册了响应拦截器', () => {
    expect(request.interceptors.response.handlers.length).toBeGreaterThan(0)
  })
})
