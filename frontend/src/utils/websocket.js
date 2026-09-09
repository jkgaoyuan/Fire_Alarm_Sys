/**
 * 实时监控 WebSocket 客户端（F-12 / FR-013）
 *
 * 只做「连接质量」这一层：Ticket 换取、指数退避重连、last_msg_id 续传、心跳与去重。
 * 业务语义（列表置顶、提示音、统计刷新）全部交给 stores/monitor.js，便于单测。
 */

const LAST_MSG_KEY = 'fire_alarm_ws_last_msg_id'

/** 1/2/4/8/16/30s 后退避到上限，避免后端重启时把请求打满（计划 F-12） */
export const RECONNECT_STEPS_MS = [1000, 2000, 4000, 8000, 16000, 30000]

/** 服务端每 30s 主动 pong，客户端再各发一次 ping 以探测半开连接 */
export const HEARTBEAT_MS = 15000

/** 多实例部署下同一帧可能重复送达，按 Stream id 去重（计划 十一） */
export const SEEN_LIMIT = 2000

export function retryDelay(attempt, steps = RECONNECT_STEPS_MS) {
  const index = Math.min(Math.max(attempt, 0), steps.length - 1)
  return steps[index]
}

/**
 * WS 地址：开发用 VITE_WS_URL，生产与 API 同源（http→ws / https→wss）
 */
export function wsEndpoint() {
  const configured = import.meta.env.VITE_WS_URL
  if (configured) return `${configured.replace(/\/+$/, '')}/devices`
  const api = import.meta.env.VITE_API_BASE_URL || ''
  const match = /^(https?):\/\/([^/]+)/i.exec(api)
  if (match) {
    const scheme = match[1].toLowerCase() === 'https' ? 'wss:' : 'ws:'
    return `${scheme}//${match[2]}/ws/devices`
  }
  const loc = globalThis.location
  const scheme = loc && loc.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${loc ? loc.host : 'localhost:8000'}/ws/devices`
}

export function readLastMsgId() {
  try {
    return sessionStorage.getItem(LAST_MSG_KEY) || ''
  } catch {
    return ''
  }
}

export function writeLastMsgId(id) {
  if (!id) return
  try {
    sessionStorage.setItem(LAST_MSG_KEY, id)
  } catch {
    // 隐私模式下 sessionStorage 会抛错，丢掉落点续传不影响实时推送
  }
}

export class RealtimeClient {
  /**
   * @param {Object} options
   * @param {() => Promise<{data?: {ticket: string}}>} options.fetchTicket 换取一次性握手 Ticket
   * @param {(frame: Object) => void} options.onFrame 收到帧回调（已去重）
   * @param {(state: string, detail?: Object) => void} [options.onState]
   * @param {(url: string) => Object} [options.createSocket] 注入点，便于单测
   */
  constructor({ fetchTicket, onFrame, onState, createSocket, endpoint = wsEndpoint }) {
    this.fetchTicket = fetchTicket
    this.onFrame = onFrame || (() => {})
    this.onState = onState || (() => {})
    this.createSocket = createSocket || ((url) => new WebSocket(url))
    this.endpoint = endpoint

    this.state = 'idle'
    this.attempt = 0
    this.lastMsgId = readLastMsgId()
    this.socket = null
    this.lastFrameAt = null
    this._seen = new Set()
    this._heartbeat = null
    this._retry = null
    this._stopped = true
  }

  get connected() {
    return this.state === 'open'
  }

  connect() {
    if (this._stopped) {
      this._stopped = false
      this._open('connecting')
    }
  }

  close() {
    this._stopped = true
    this.attempt = 0
    this._clearTimers()
    const socket = this.socket
    this.socket = null
    if (socket) {
      socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null
      try {
        socket.close()
      } catch {
        // 已关闭的连接再 close 会抛错，忽略
      }
    }
    this._setState('closed')
  }

  /**
   * 发送控制帧（ping / subscribe）。非连接态静默返回 false：
   * 心跳定时器与视图切换都可能在不确定时刻调用它，不能靠调用方判状态。
   */
  send(payload) {
    if (this.state !== 'open' || !this.socket) return false
    try {
      this.socket.send(JSON.stringify(payload))
      return true
    } catch {
      return false
    }
  }

  /** 服务端要求全量刷新时，断点已无意义：清掉避免下次握手再次溢出 */
  resetResyncPoint() {
    this.lastMsgId = ''
    writeLastMsgId('')
    this._seen.clear()
  }

  async _open(stateName) {
    this._clearTimers()
    this._setState(stateName)

    let ticket
    try {
      // Ticket 一次性：每次（重）连都必须重新换取
      const res = await this.fetchTicket()
      ticket = res?.data?.ticket
    } catch {
      this._scheduleReconnect()
      return
    }
    if (!ticket) {
      this._scheduleReconnect()
      return
    }

    const params = new URLSearchParams({ ticket })
    if (this.lastMsgId) params.set('last_msg_id', this.lastMsgId)
    let socket
    try {
      socket = this.createSocket(`${this.endpoint()}?${params.toString()}`)
    } catch {
      this._scheduleReconnect()
      return
    }
    this.socket = socket
    socket.onopen = () => this._onSocketOpen()
    socket.onmessage = (event) => this._onSocketMessage(event)
    socket.onclose = () => this._onSocketClose()
    socket.onerror = () => this._onSocketError()
  }

  _onSocketOpen() {
    if (!this.socket) return
    this.attempt = 0
    this._setState('open')
    this._heartbeat = setInterval(() => this.send({ action: 'ping' }), HEARTBEAT_MS)
  }

  _onSocketMessage(event) {
    let frame
    try {
      frame = JSON.parse(event.data)
    } catch {
      return
    }
    if (!frame || typeof frame !== 'object') return

    this.lastFrameAt = Date.now()
    if (frame.id) {
      if (this._seen.has(frame.id)) return
      this._seen.add(frame.id)
      if (this._seen.size > SEEN_LIMIT) {
        this._seen.delete(this._seen.values().next().value)
      }
      this.lastMsgId = frame.id
      writeLastMsgId(frame.id)
    }
    this.onFrame(frame)
  }

  _onSocketClose() {
    this._clearTimers()
    this.socket = null
    if (!this._stopped) this._scheduleReconnect()
    else this._setState('closed')
  }

  _onSocketError() {
    // 浏览器随后会触发 close，重连统一由 close 处理
  }

  _scheduleReconnect() {
    this._clearTimers()
    const delay = retryDelay(this.attempt)
    this.attempt += 1
    this._setState('reconnecting', { attempt: this.attempt, delay })
    this._retry = setTimeout(() => {
      if (!this._stopped) this._open('reconnecting')
    }, delay)
  }

  _clearTimers() {
    if (this._heartbeat) {
      clearInterval(this._heartbeat)
      this._heartbeat = null
    }
    if (this._retry) {
      clearTimeout(this._retry)
      this._retry = null
    }
  }

  _setState(state, detail) {
    this.state = state
    this.onState(state, detail || {})
  }
}
