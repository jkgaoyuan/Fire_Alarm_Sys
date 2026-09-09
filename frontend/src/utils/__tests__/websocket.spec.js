import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  RealtimeClient,
  RECONNECT_STEPS_MS,
  retryDelay,
  readLastMsgId,
  writeLastMsgId,
} from '../websocket'

const LAST_MSG_KEY = 'fire_alarm_ws_last_msg_id'

class FakeSocket {
  constructor(url) {
    this.url = url
    this.sent = []
    this.closed = false
    FakeSocket.instances.push(this)
  }

  send(data) {
    this.sent.push(data)
  }

  close() {
    this.closed = true
  }

  emitMessage(payload) {
    this.onmessage?.({ data: typeof payload === 'string' ? payload : JSON.stringify(payload) })
  }

  emitClose() {
    this.onclose?.({ code: 1006 })
  }
}

function makeClient(overrides = {}) {
  FakeSocket.instances = []
  const fetchTicket = overrides.fetchTicket || vi.fn().mockResolvedValue({ data: { ticket: 'tk-1' } })
  const client = new RealtimeClient({
    fetchTicket,
    onFrame: overrides.onFrame || vi.fn(),
    onState: overrides.onState || vi.fn(),
    endpoint: () => 'ws://test/ws/devices',
    createSocket: (url) => new FakeSocket(url),
    ...overrides,
  })
  return { client, fetchTicket }
}

/** _open 里 await 取票后还有若干微任务，单轮让出不足以保证新 socket 已建立 */
async function flush(turns = 6) {
  for (let i = 0; i < turns; i += 1) await Promise.resolve()
}

describe('websocket 客户端', () => {
  beforeEach(() => {
    sessionStorage.clear()
    FakeSocket.instances = []
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('重连按 1/2/4/8/16/30s 指数退避并在上限封顶', () => {
    expect(RECONNECT_STEPS_MS).toEqual([1000, 2000, 4000, 8000, 16000, 30000])
    expect(RECONNECT_STEPS_MS.map((_, attempt) => retryDelay(attempt))).toEqual(RECONNECT_STEPS_MS)
    expect(retryDelay(6)).toBe(30000)
    expect(retryDelay(99)).toBe(30000)
    expect(retryDelay(-1)).toBe(1000)
  })

  it('记录帧 id 到 sessionStorage 并在重连时携带 last_msg_id', async () => {
    const { client } = makeClient()
    client.connect()
    await flush()

    const socket = FakeSocket.instances[0]
    expect(socket.url).toContain('ticket=tk-1')
    expect(socket.url).not.toContain('last_msg_id')

    socket.onopen()
    socket.emitMessage({ id: '1725000000000-0', type: 'pong' })
    expect(readLastMsgId()).toBe('1725000000000-0')

    vi.useFakeTimers()
    socket.emitClose()
    vi.advanceTimersByTime(1000)
    await flush()
    vi.useRealTimers()

    const reconnected = FakeSocket.instances[1]
    expect(reconnected.url).toContain('last_msg_id=1725000000000-0')
    client.close()
  })

  it('每次（重）连都重新换取一次性 Ticket', async () => {
    let seq = 0
    const fetchTicket = vi.fn().mockImplementation(() => Promise.resolve({ data: { ticket: `tk-${++seq}` } }))
    const { client } = makeClient({ fetchTicket })

    client.connect()
    await flush()
    expect(FakeSocket.instances[0].url).toContain('ticket=tk-1')

    vi.useFakeTimers()
    FakeSocket.instances[0].emitClose()
    vi.advanceTimersByTime(1000)
    await flush()
    vi.useRealTimers()

    expect(fetchTicket).toHaveBeenCalledTimes(2)
    expect(FakeSocket.instances[1].url).toContain('ticket=tk-2')
    client.close()
  })

  it('非连接态 send 与 Ticket 失败都不抛错', async () => {
    const { client } = makeClient({ fetchTicket: vi.fn().mockRejectedValue(new Error('403')) })
    expect(client.send({ action: 'ping' })).toBe(false)

    vi.useFakeTimers()
    client.connect()
    await flush()
    expect(FakeSocket.instances).toHaveLength(0)
    // 取票失败也要进入退避重连，而不是把连接状态卡死
    expect(client.state).toBe('reconnecting')
    vi.advanceTimersByTime(1000)
    await flush()
    vi.useRealTimers()

    writeLastMsgId('')
    expect(client.send({ action: 'ping' })).toBe(false)
    client.close()
    expect(client.send({ action: 'ping' })).toBe(false)
  })
})
