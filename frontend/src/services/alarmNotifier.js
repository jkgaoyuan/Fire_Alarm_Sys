/**
 * 报警声光提示（F-15 / FR-017）
 *
 * 分级提示音 + 桌面通知，二者都是"能不用就不用"的增强能力：
 * 浏览器自动播放策略、无 Notification 权限、文件缺失都必须静默降级而不是抛错，
 * 因为这条路径运行在实时推送回调里，抛错会中断整个帧分发。
 */

const MUTE_KEY = 'fire_alarm_global_muted'

/** FR-017 四级提示音；alarm_type 与后端 ALARM_TYPE_PROFILE 一致 */
export const AUDIO_SOURCES = {
  fire: '/audio/fire.mp3',
  pre_fire: '/audio/pre_fire.mp3',
  fault: '/audio/fault.mp3',
  shield: '/audio/shield.mp3',
}

/** 火警/预警必须持续鸣响直到人工消音或处置完成，故障与屏蔽响一次即可 */
export const LOOPING_ALARM_TYPES = new Set(['fire', 'pre_fire'])

export const ALARM_TYPE_LABELS = {
  fire: '火警',
  pre_fire: '预警',
  fault: '故障',
  shield: '屏蔽',
}

export function readGlobalMuted() {
  try {
    return localStorage.getItem(MUTE_KEY) === '1'
  } catch {
    return false
  }
}

export function writeGlobalMuted(muted) {
  try {
    localStorage.setItem(MUTE_KEY, muted ? '1' : '0')
  } catch {
    // 隐私模式下持久化失败，本次会话内仍然生效
  }
}

export function resolveAudioSource(alarmType) {
  return AUDIO_SOURCES[alarmType] || null
}

export function shouldLoop(alarmType) {
  return LOOPING_ALARM_TYPES.has(alarmType)
}

export function buildNotificationBody(alarm) {
  const place = [alarm.org_name, alarm.location_description].filter(Boolean).join(' · ')
  const device = alarm.device_name || alarm.device_code || `设备 ${alarm.device_id}`
  return place ? `${device}｜${place}` : device
}

export class AlarmNotifier {
  /**
   * @param {Object} [options] 注入点，便于单测替换 Audio / Notification
   */
  constructor({ AudioImpl, NotificationImpl, muted } = {}) {
    // 只在未提供时回落浏览器全局；显式传 null 表示该能力不可用（老浏览器 / 单测）
    this.AudioImpl = AudioImpl === undefined ? globalThis.Audio || null : AudioImpl
    this.NotificationImpl =
      NotificationImpl === undefined ? globalThis.Notification || null : NotificationImpl
    this.muted = muted === undefined ? readGlobalMuted() : !!muted
    /** alarm_id → { audio, source } 正在鸣响的报警 */
    this._playing = new Map()
    this._unlocked = false
    this._errors = []
  }

  /**
   * 解锁自动播放（计划 十二：浏览器策略要求用户手势）。
   * 必须在手势回调里同步触发 play()，因此这里不做任何 await 前置。
   */
  unlock() {
    if (this._unlocked || !this.AudioImpl) return this._unlocked
    try {
      const audio = new this.AudioImpl(AUDIO_SOURCES.fire)
      audio.volume = 0
      const result = audio.play()
      if (result && typeof result.then === 'function') {
        result.then(
          () => {
            this._unlocked = true
            audio.pause()
          },
          () => this._recordError('自动播放仍被拦截，需要再次用户交互')
        )
      } else {
        this._unlocked = true
        audio.pause()
      }
    } catch {
      this._recordError('自动播放解锁失败，报警音可能被拦截')
    }
    return this._unlocked
  }

  setMuted(muted) {
    this.muted = !!muted
    writeGlobalMuted(this.muted)
    if (this.muted) this.stopAll()
    return this.muted
  }

  toggleMuted() {
    return this.setMuted(!this.muted)
  }

  /** Notification 权限申请；浏览器不支持或用户拒绝都返回 false */
  async ensureNotificationPermission() {
    const Impl = this.NotificationImpl
    if (!Impl) return false
    if (Impl.permission === 'granted') return true
    if (Impl.permission === 'denied') return false
    try {
      const result = await Impl.requestPermission()
      return result === 'granted'
    } catch {
      return false
    }
  }

  /**
   * 一条新报警 → 提示音 + 桌面通知。
   * 静音时整体不响应；音频失败只回退通知，通知也失败则只留记录。
   */
  async notify(alarm) {
    if (!alarm || this.muted) return { sound: false, notification: false }
    const sound = await this._playAlarm(alarm)
    const notification = this._notifyText(alarm)
    return { sound, notification }
  }

  /** FR-016.1 单条消音 / 处置完成：只停这一条的鸣响 */
  silence(alarmId) {
    const entry = this._playing.get(alarmId)
    if (!entry) return false
    this._stopEntry(entry)
    this._playing.delete(alarmId)
    return true
  }

  stopAll() {
    for (const entry of this._playing.values()) this._stopEntry(entry)
    this._playing.clear()
  }

  /** 组件卸载 / 登出：停止鸣响并释放引用，避免循环音频泄漏 */
  dispose() {
    this.stopAll()
    this._errors = []
  }

  async _playAlarm(alarm) {
    const source = resolveAudioSource(alarm.alarm_type)
    if (!source || !this.AudioImpl) return false
    if (this._playing.has(alarm.alarm_id)) return true

    const audio = new this.AudioImpl(source)
    audio.loop = shouldLoop(alarm.alarm_type)
    // 自动播放被拦截时 play() 的 Promise 会 reject，不会同步抛错
    audio.onerror = () => this._recordError(`音频加载失败: ${source}`)
    this._playing.set(alarm.alarm_id, { audio, source })
    try {
      await audio.play()
      return true
    } catch {
      this._stopEntry({ audio })
      this._playing.delete(alarm.alarm_id)
      this._recordError('浏览器拦截了自动播放，需要用户交互后才能鸣响')
      return false
    }
  }

  _notifyText(alarm) {
    const Impl = this.NotificationImpl
    if (!Impl) return false
    if (Impl.permission && Impl.permission !== 'granted') return false
    const label = ALARM_TYPE_LABELS[alarm.alarm_type] || '报警'
    try {
      // eslint-disable-next-line no-new
      new Impl(`【${label}】${alarm.device_name || alarm.device_code || ''}`, {
        body: buildNotificationBody(alarm),
        tag: `alarm-${alarm.alarm_id}`,
        icon: '/favicon.ico',
      })
      return true
    } catch {
      this._recordError('桌面通知创建失败')
      return false
    }
  }

  _stopEntry(entry) {
    if (!entry) return
    try {
      entry.audio.pause()
      entry.audio.currentTime = 0
    } catch {
      // 已销毁的 Audio 元素再操作会抛错，无需处理
    }
  }

  _recordError(message) {
    if (this._errors.length < 20) this._errors.push(message)
  }
}

/** 全应用共享一个实例：多个页面同时挂载时不能各自鸣响 */
export const alarmNotifier = new AlarmNotifier()

export default alarmNotifier
