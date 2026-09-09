import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  AlarmNotifier,
  AUDIO_SOURCES,
  buildNotificationBody,
  resolveAudioSource,
  shouldLoop,
} from '../alarmNotifier'

const MUTE_KEY = 'fire_alarm_global_muted'

/** Node 24 的实验性全局 localStorage 会遮蔽 jsdom 实现，测试内自行注入（同 auth.spec） */
function createMemoryStorage() {
  let store = {}
  return {
    getItem: (key) => store[key] ?? null,
    setItem: (key, value) => {
      store[key] = String(value)
    },
    removeItem: (key) => {
      delete store[key]
    },
    clear: () => {
      store = {}
    },
  }
}

function audioStub({ failPlay = false } = {}) {
  const instances = []
  return {
    instances,
    Audio: class {
      constructor(src) {
        this.src = src
        this.loop = false
        this.paused = true
        this.currentTime = 0
        instances.push(this)
      }

      play() {
        if (failPlay) return Promise.reject(new Error('NotAllowedError'))
        this.paused = false
        return Promise.resolve()
      }

      pause() {
        this.paused = true
      }
    },
  }
}

function notificationStub(permission = 'granted') {
  const instances = []
  class Notification {
    constructor(title, options) {
      this.title = title
      this.options = options
      instances.push(this)
    }
  }
  Notification.instances = instances
  Notification.permission = permission
  return Notification
}

function withPermission(Notification, permission) {
  Notification.permission = permission
  return Notification
}

const FIRE = {
  alarm_id: 88,
  device_id: 12,
  device_code: 'DEV-SMK-001',
  device_name: '1F大厅烟感A01',
  org_name: '1F大厅',
  alarm_type: 'fire',
  status: 'pending',
  location_description: '东侧走廊',
}

describe('alarmNotifier 分级提示音', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createMemoryStorage())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('按报警类型选择音频，火警循环播放、故障响一次', async () => {
    const audio = audioStub()
    const notification = withPermission(notificationStub(), 'granted')
    const notifier = new AlarmNotifier({
      AudioImpl: audio.Audio,
      NotificationImpl: notification,
      muted: false,
    })

    await notifier.notify(FIRE)
    expect(audio.instances[0].src).toBe(AUDIO_SOURCES.fire)
    expect(audio.instances[0].loop).toBe(true)
    expect(notification.permission).toBe('granted')

    await notifier.notify({ ...FIRE, alarm_id: 89, alarm_type: 'fault' })
    expect(audio.instances[1].src).toBe(AUDIO_SOURCES.fault)
    expect(audio.instances[1].loop).toBe(false)

    expect(resolveAudioSource('unknown')).toBeNull()
    expect(shouldLoop('pre_fire')).toBe(true)
  })

  it('通知与音频任一不可用时静默降级，不抛错', async () => {
    // 自动播放被拦截 → 回退桌面通知文本
    const blockedAudio = audioStub({ failPlay: true })
    const granted = withPermission(notificationStub(), 'granted')
    const soundOnly = new AlarmNotifier({
      AudioImpl: blockedAudio.Audio,
      NotificationImpl: granted,
      muted: false,
    })
    const blocked = await soundOnly.notify(FIRE)
    expect(blocked.sound).toBe(false)
    expect(blocked.notification).toBe(true)
    expect(granted.instances[0].title).toBe('【火警】1F大厅烟感A01')
    expect(soundOnly._playing.size).toBe(0)
    expect(soundOnly._errors.length).toBeGreaterThan(0)

    // 通知未授权 → 只剩提示音
    const okAudio = audioStub()
    const denied = withPermission(notificationStub(), 'denied')
    const silentNotify = new AlarmNotifier({
      AudioImpl: okAudio.Audio,
      NotificationImpl: denied,
      muted: false,
    })
    expect(await silentNotify.notify(FIRE)).toEqual({ sound: true, notification: false })
    expect(await silentNotify.ensureNotificationPermission()).toBe(false)

    // 两种能力都没有（老浏览器 / jsdom）时不能抛错
    const bare = new AlarmNotifier({ AudioImpl: null, NotificationImpl: null, muted: false })
    expect(await bare.notify(FIRE)).toEqual({ sound: false, notification: false })
    expect(await bare.ensureNotificationPermission()).toBe(false)
  })

  it('全局静音后不再播放，单条消音只停该条', async () => {
    const audio = audioStub()
    const notification = withPermission(notificationStub(), 'granted')
    const notifier = new AlarmNotifier({
      AudioImpl: audio.Audio,
      NotificationImpl: notification,
      muted: false,
    })

    await notifier.notify(FIRE)
    await notifier.notify({ ...FIRE, alarm_id: 90, alarm_type: 'pre_fire' })
    expect(audio.instances).toHaveLength(2)

    expect(notifier.silence(88)).toBe(true)
    expect(audio.instances[0].paused).toBe(true)
    expect(audio.instances[1].paused).toBe(false)
    expect(notifier.silence(88)).toBe(false)

    notifier.setMuted(true)
    expect(localStorage.getItem(MUTE_KEY)).toBe('1')
    expect(audio.instances[1].paused).toBe(true)

    const before = audio.instances.length
    expect((await notifier.notify({ ...FIRE, alarm_id: 91 })).sound).toBe(false)
    expect(audio.instances).toHaveLength(before)

    notifier.toggleMuted()
    expect(localStorage.getItem(MUTE_KEY)).toBe('0')
    await notifier.notify({ ...FIRE, alarm_id: 92 })
    expect(audio.instances).toHaveLength(before + 1)

    notifier.dispose()
    expect(notifier._playing.size).toBe(0)
  })
})

describe('alarmNotifier 通知文案', () => {
  it('缺少位置信息时只展示设备', () => {
    expect(buildNotificationBody(FIRE)).toBe('1F大厅烟感A01｜1F大厅 · 东侧走廊')
    expect(buildNotificationBody({ device_code: 'DEV-1' })).toBe('DEV-1')
  })
})
