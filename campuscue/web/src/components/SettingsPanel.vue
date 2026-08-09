<script setup>
/**
 * The two things about the current group that only the student knows.
 *
 * First, what the group *is*. Naming it 软件工程 is not decoration: the L2 prompt
 * renders it as 对应课程, so a bare "实验三周五交" becomes a 软件工程 deadline for
 * the extractor. This is the one screen in the product where typing makes the AI
 * more accurate rather than merely correcting it afterwards.
 *
 * Second, when to be told. Lead times are offered as chips rather than a minutes
 * field because nobody thinks in 2880: they think "两天前". The chips are the
 * vocabulary; the wire is still minutes.
 *
 * One dialog for both, because they answer the same question -- "how should
 * 课讯 treat this group" -- and two separate settings screens for one group would
 * be worse than one screen with two sections.
 *
 * The third section is the exception: delivery settings are global, not per-group.
 * They live here anyway, marked 全局, because a student looking for "where do the
 * messages go" opens 设置 and does not care which of two settings screens owns it.
 * The 全局 marker is the honest part -- these four switches look identical to the
 * per-group ones above and changing one changes it everywhere.
 */
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  /** The group being configured, as it appears in the picker. */
  source: { type: Object, default: null },
  profile: { type: Object, default: null },
  /** Global delivery settings, from GET /campus/notify. */
  notify: { type: Object, default: null },
  /** Result of the last 试一下, from POST /campus/notify/test. */
  notifyTest: { type: Object, default: null },
  testing: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
  /** Result of the last 导入, from POST /campus/import: `{ ok, text }`. */
  transferResult: { type: Object, default: null },
  transferBusy: { type: Boolean, default: false },
})

const emit = defineEmits([
  'save',
  'close',
  'test-notify',
  'delete-source',
  'export-tasks',
  'import-tasks',
  'export-backup',
  'restore-backup',
])

const TYPES = [
  { value: 'homework', label: '作业' },
  { value: 'exam', label: '考试' },
  { value: 'competition', label: '比赛' },
  { value: 'activity', label: '活动' },
  { value: 'notice', label: '通知' },
]

const SOURCE_TYPES = [
  { value: 'course', label: '课程群' },
  { value: 'competition', label: '赛事群' },
  { value: 'admin', label: '通知群' },
  { value: 'club', label: '社团群' },
  { value: 'other', label: '其它' },
]

/** The lead-time vocabulary, in minutes. Anything the student already has that
 *  is not in this list still shows as a chip -- see `chipsFor` -- so a value set
 *  from the API or the DB is never silently dropped by the UI. */
const LEADS = [
  { minutes: 10080, label: '一周前' },
  { minutes: 4320, label: '三天前' },
  { minutes: 2880, label: '两天前' },
  { minutes: 1440, label: '一天前' },
  { minutes: 720, label: '12小时前' },
  { minutes: 180, label: '3小时前' },
  { minutes: 120, label: '2小时前' },
  { minutes: 60, label: '1小时前' },
  { minutes: 30, label: '30分钟前' },
]

const courseName = ref('')
const displayName = ref('')
const sourceType = ref('course')
const enabled = ref(true)

const leads = ref({})
const quietStart = ref('23:00')
const quietEnd = ref('07:30')
const threshold = ref(0.7)
const autoConfirm = ref(false)

/** Delivery. `targetMode` splits the picker in two because the two kinds of
 *  target are found in different ways: a watched group can be listed, but the
 *  student's own QQ number is something only they know -- the backend only ever
 *  sees the bot's uin. */
const targetMode = ref('group')
const targetUmo = ref('')
const friendId = ref('')
const onDetect = ref(true)
const desktopToast = ref(true)
const deadlineReminders = ref(true)

watch(
  () => [props.open, props.source, props.profile, props.notify],
  () => {
    const source = props.source
    if (source) {
      courseName.value = source.course_name || ''
      // The picker's label falls back to a readable umo, which is not a name the
      // student typed -- showing it in the field would turn "no display name" into
      // an accidental one on the next save.
      displayName.value = source.display_name || ''
      sourceType.value = source.source_type || 'course'
      enabled.value = source.enabled !== false
    }
    const profile = props.profile
    if (profile) {
      leads.value = Object.fromEntries(
        TYPES.map((t) => [t.value, [...(profile.lead_minutes?.[t.value] || [])]]),
      )
      quietStart.value = profile.quiet_hours?.start || '23:00'
      quietEnd.value = profile.quiet_hours?.end || '07:30'
      threshold.value = profile.confidence_threshold ?? 0.7
      autoConfirm.value = Boolean(profile.auto_confirm)
    }
    const nf = props.notify
    if (nf) {
      onDetect.value = nf.on_detect !== false
      desktopToast.value = nf.desktop_toast !== false
      deadlineReminders.value = nf.deadline_reminders !== false
      targetUmo.value = nf.target_umo || ''
      const prefix = nf.friend_umo_prefix || ''
      // A saved private-chat target comes back as a umo; splitting the number
      // back out is what lets the field show 20002 instead of the raw string.
      if (prefix && targetUmo.value.startsWith(prefix)) {
        targetMode.value = 'friend'
        friendId.value = targetUmo.value.slice(prefix.length)
      } else {
        targetMode.value = 'group'
        friendId.value = ''
      }
    }
    // Move focus into the dialog on open, for keyboard and screen-reader users.
    if (props.open) {
      nextTick(() => {
        const sheet = document.querySelector('.scrim .sheet')
        if (sheet) sheet.focus()
      })
    }
  },
  { immediate: true },
)

/** What would be saved as the target, given the mode. Empty means "not chosen",
 *  which is a legitimate state -- delivery falls back to the source group. */
const resolvedTarget = computed(() => {
  if (targetMode.value === 'friend') {
    const id = friendId.value.trim()
    return id ? `${props.notify?.friend_umo_prefix || ''}${id}` : ''
  }
  return targetUmo.value
})

const targetLabel = computed(() => {
  const target = resolvedTarget.value
  if (!target) return '还没指定，暂时发回消息来源的群'
  if (targetMode.value === 'friend') return `QQ私聊 ${friendId.value.trim()}`
  const hit = (props.notify?.candidates || []).find((c) => c.umo === target)
  return hit?.label || target
})

/** A private-chat target only works if the number is the student's own and the
 *  bot is their friend. Neither is checkable from here, so the panel says so
 *  rather than implying a saved value is a working one. */
const friendIdLooksWrong = computed(
  () => targetMode.value === 'friend' && /\D/.test(friendId.value.trim()),
)

/** The offered chips plus any the student already has that we do not offer, so
 *  an unusual lead time set elsewhere survives a visit to this dialog. */
function chipsFor(type) {
  const own = leads.value[type] || []
  const extra = own
    .filter((m) => !LEADS.some((l) => l.minutes === m))
    .map((m) => ({ minutes: m, label: `${m}分钟前` }))
  return [...LEADS, ...extra].sort((a, b) => b.minutes - a.minutes)
}

function isOn(type, minutes) {
  return (leads.value[type] || []).includes(minutes)
}

function toggleLead(type, minutes) {
  const own = new Set(leads.value[type] || [])
  if (own.has(minutes)) own.delete(minutes)
  else own.add(minutes)
  leads.value = {
    ...leads.value,
    [type]: [...own].sort((a, b) => b - a),
  }
}

const sourceChanges = computed(() => {
  const source = props.source
  if (!source) return {}
  const next = {}
  if (courseName.value.trim() !== (source.course_name || '')) {
    next.course_name = courseName.value.trim()
  }
  if (displayName.value.trim() !== (source.display_name || '')) {
    next.display_name = displayName.value.trim()
  }
  if (sourceType.value !== (source.source_type || 'course')) {
    next.source_type = sourceType.value
  }
  if (enabled.value !== (source.enabled !== false)) next.enabled = enabled.value
  return next
})

const profileChanges = computed(() => {
  const profile = props.profile
  if (!profile) return {}
  const next = {}
  const before = profile.lead_minutes || {}
  const changed = TYPES.some(
    (t) =>
      (leads.value[t.value] || []).join(',') !== (before[t.value] || []).join(','),
  )
  if (changed) next.lead_minutes = leads.value
  if (
    quietStart.value !== (profile.quiet_hours?.start || '') ||
    quietEnd.value !== (profile.quiet_hours?.end || '')
  ) {
    next.quiet_hours = { start: quietStart.value, end: quietEnd.value }
  }
  if (Number(threshold.value) !== profile.confidence_threshold) {
    next.confidence_threshold = Number(threshold.value)
  }
  if (autoConfirm.value !== Boolean(profile.auto_confirm)) {
    next.auto_confirm = autoConfirm.value
  }
  return next
})

const notifyChanges = computed(() => {
  const nf = props.notify
  if (!nf) return {}
  const next = {}
  if (resolvedTarget.value !== (nf.target_umo || '')) {
    next.target_umo = resolvedTarget.value
  }
  if (onDetect.value !== (nf.on_detect !== false)) next.on_detect = onDetect.value
  if (desktopToast.value !== (nf.desktop_toast !== false)) {
    next.desktop_toast = desktopToast.value
  }
  if (deadlineReminders.value !== (nf.deadline_reminders !== false)) {
    next.deadline_reminders = deadlineReminders.value
  }
  return next
})

const dirty = computed(
  () =>
    Object.keys(sourceChanges.value).length > 0 ||
    Object.keys(profileChanges.value).length > 0 ||
    Object.keys(notifyChanges.value).length > 0,
)

/** A group with no lead times at all would never be reminded about anything --
 *  the product's whole claim, switched off by unchecking chips one at a time.
 *  Only a warning when the detection push is off too: with it on, the student
 *  still hears about everything the moment it is found. */
const silent = computed(
  () =>
    !onDetect.value && TYPES.every((t) => !(leads.value[t.value] || []).length),
)

/** Both channels off means 课讯 reads the group and never says anything. It still
 *  fills the board, so this is a legitimate choice -- but not an accidental one. */
const mute = computed(() => !onDetect.value && !deadlineReminders.value)

/** One emit for all three. Separate ones would race on the parent's saving flag
 *  and the first to finish would clear it while the others were still in flight. */
function save() {
  if (!dirty.value) return
  emit('save', {
    source: Object.keys(sourceChanges.value).length ? sourceChanges.value : null,
    profile: Object.keys(profileChanges.value).length ? profileChanges.value : null,
    notify: Object.keys(notifyChanges.value).length ? notifyChanges.value : null,
  })
}

/** Testing before saving would test the stored settings, not the ones on screen.
 *  Saving first is the honest order, and it is also what the student means. */
function testNotify() {
  emit('test-notify', {
    pending: Object.keys(notifyChanges.value).length ? notifyChanges.value : null,
  })
}

function requestDelete() {
  if (!props.source?.umo) return
  emit('delete-source', props.source)
}

/** Moving tasks between installs. The file is handed up rather than read here:
 *  the parent owns every other call to the API, and a component that fetched on
 *  its own would also have to own reloading the board afterwards. */
const fileInput = ref(null)
const backupInput = ref(null)
const importOverwrite = ref(false)
const importHere = ref(false)

function requestExport() {
  emit('export-tasks')
}

function pickFile() {
  fileInput.value?.click()
}

function onFilePicked(event) {
  const file = event.target.files?.[0]
  // Reset first: picking the same file twice in a row fires no change event
  // otherwise, which reads as the button having stopped working.
  event.target.value = ''
  if (!file) return
  emit('import-tasks', {
    file,
    overwrite: importOverwrite.value,
    umo: importHere.value ? props.source?.umo || '' : '',
  })
}

function pickBackup() {
  backupInput.value?.click()
}

function onBackupPicked(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file) emit('restore-backup', { file })
}
</script>

<template>
  <div v-if="open" class="scrim" @click.self="$emit('close')">
    <div
      class="sheet"
      role="dialog"
      aria-label="群设置"
      tabindex="-1"
      @keydown.esc="$emit('close')"
    >
      <header class="head">
        <div>
          <h2>群设置</h2>
          <p class="who">{{ source?.label || '当前群' }}</p>
        </div>
        <button class="close" type="button" aria-label="关闭" @click="$emit('close')">
          ✕
        </button>
      </header>

      <form class="form" @submit.prevent="save">
        <section class="block">
          <h3>
            完整备份 <span class="tag">全局</span>
          </h3>
          <p class="hint block-hint">
            用于故障恢复，包含全部任务、群设置、提醒偏好和 AI 溯源原文。不包含
            API Key、QQ 登录态或 NapCat 文件；备份本身含私人信息，请妥善保管。
          </p>

          <div class="testrow">
            <button
              class="btn"
              type="button"
              :disabled="transferBusy"
              @click="$emit('export-backup')"
            >
              下载完整备份
            </button>
            <button
              class="btn btn-danger"
              type="button"
              :disabled="transferBusy"
              @click="pickBackup"
            >
              恢复完整备份
            </button>
            <input
              ref="backupInput"
              class="hidden-file"
              type="file"
              accept="application/json,.json"
              @change="onBackupPicked"
            />
          </div>
        </section>

        <section class="block">
          <h3>这个群是什么</h3>
          <label class="field">
            <span class="lbl">对应课程</span>
            <input
              v-model="courseName"
              class="input"
              type="text"
              placeholder="例如：软件工程"
              autocomplete="off"
            />
            <!-- The one place a student's typing improves future extractions
                 rather than only fixing past ones. Worth saying out loud. -->
            <span class="hint">
              填了之后会写进 AI 的判断依据，群里说「实验三周五交」就知道是这门课的。
            </span>
          </label>

          <label class="field">
            <span class="lbl">显示名称</span>
            <input
              v-model="displayName"
              class="input"
              type="text"
              :placeholder="source?.label || ''"
              autocomplete="off"
            />
            <span class="hint">只影响看板上怎么称呼它，留空就用课程名。</span>
          </label>

          <label class="field">
            <span class="lbl">群类型</span>
            <select v-model="sourceType" class="input">
              <option v-for="t in SOURCE_TYPES" :key="t.value" :value="t.value">
                {{ t.label }}
              </option>
            </select>
          </label>

          <label class="check">
            <input v-model="enabled" type="checkbox" />
            <span>
              监听这个群
              <span class="hint">
                取消后不再读它的新消息，已有任务和统计都留着。
              </span>
            </span>
          </label>

          <div class="danger">
            <button
              class="btn btn-danger"
              type="button"
              :disabled="!source?.umo || saving"
              @click="requestDelete"
            >
              删除这个群
            </button>
            <span class="hint">
              连它抽出来的任务和提醒一起删掉，不能撤销。用来清掉测试用的假群。
            </span>
          </div>
        </section>

        <section class="block">
          <h3>提前多久提醒</h3>
          <p class="hint block-hint">
            按任务类型分别设置，可以多选。改完会把已排的提醒全部重排一遍。
          </p>

          <div v-for="t in TYPES" :key="t.value" class="leadrow">
            <span class="leadname">{{ t.label }}</span>
            <div class="chips">
              <button
                v-for="chip in chipsFor(t.value)"
                :key="chip.minutes"
                class="chip"
                :class="{ on: isOn(t.value, chip.minutes) }"
                type="button"
                :aria-pressed="isOn(t.value, chip.minutes)"
                @click="toggleLead(t.value, chip.minutes)"
              >
                {{ chip.label }}
              </button>
            </div>
          </div>

          <p v-if="silent" class="warn">
            所有类型都没有提醒时间，这样课讯不会再主动提醒你任何事。
          </p>
        </section>

        <section v-if="notify" class="block">
          <h3>
            消息发到哪 <span class="tag">全局</span>
          </h3>
          <p class="hint block-hint">
            所有群探测到的信息都发到这一个会话，不会发回原来的群。
          </p>

          <div class="modes">
            <button
              class="mode"
              :class="{ on: targetMode === 'friend' }"
              type="button"
              :aria-pressed="targetMode === 'friend'"
              @click="targetMode = 'friend'"
            >
              我的 QQ 私聊
              <span class="hint">只有你看得到，推荐</span>
            </button>
            <button
              class="mode"
              :class="{ on: targetMode === 'group' }"
              type="button"
              :aria-pressed="targetMode === 'group'"
              @click="targetMode = 'group'"
            >
              某个群
              <span class="hint">整个群都看得到</span>
            </button>
          </div>

          <label v-if="targetMode === 'friend'" class="field">
            <span class="lbl">你的 QQ 号</span>
            <input
              v-model="friendId"
              class="input"
              type="text"
              inputmode="numeric"
              placeholder="例如：20002"
              autocomplete="off"
            />
            <span class="hint">
              填你自己的号，并且先加机器人为好友，否则发不过去。
            </span>
          </label>

          <label v-else class="field">
            <span class="lbl">选一个群</span>
            <select v-model="targetUmo" class="input">
              <option value="">（不指定，发回消息来源的群）</option>
              <option
                v-for="c in notify.candidates || []"
                :key="c.umo"
                :value="c.umo"
              >
                {{ c.label }}{{ c.hint ? ` · ${c.hint}` : '' }}
              </option>
            </select>
          </label>

          <p class="target">
            现在会发到：<strong>{{ targetLabel }}</strong>
          </p>
          <p v-if="friendIdLooksWrong" class="warn">QQ 号应该只有数字。</p>

          <label class="check">
            <input v-model="onDetect" type="checkbox" />
            <span>
              探测到就立刻推
              <span class="hint">
                AI 在群里认出一条有用的信息，马上把它发给你，不用等到快截止。
              </span>
            </span>
          </label>

          <label class="check" :class="{ off: notify.toast_supported === false }">
            <input
              v-model="desktopToast"
              type="checkbox"
              :disabled="notify.toast_supported === false"
            />
            <span>
              电脑弹窗
              <span class="hint">
                {{
                  notify.toast_supported === false
                    ? '当前系统不支持，这个开关不起作用（只在 Windows 上有）。'
                    : '在这台电脑右下角弹一条通知，和别的软件的提示一样。'
                }}
              </span>
            </span>
          </label>

          <label class="check">
            <input v-model="deadlineReminders" type="checkbox" />
            <span>
              临近截止再提醒一次
              <span class="hint">
                按上面「提前多久提醒」的设置再发一遍。觉得啰嗦可以关掉，探测推送不受影响。
              </span>
            </span>
          </label>

          <p v-if="mute" class="warn">
            两个都关了，课讯只会把任务放到看板上，不会主动告诉你。
          </p>

          <div class="testrow">
            <button
              class="btn btn-quiet"
              type="button"
              :disabled="testing || saving"
              @click="testNotify"
            >
              {{ testing ? '发送中…' : '试一下' }}
            </button>
            <span v-if="notifyTest" class="hint">
              <template v-if="notifyTest.pushed">
                已发到 {{ notifyTest.target }}{{
                  notifyTest.toasted ? '，弹窗也弹了' : ''
                }}，去看一眼。
              </template>
              <template v-else-if="notifyTest.toasted">
                弹窗弹了，但消息没发出去：{{ notifyTest.detail }}
              </template>
              <template v-else>没发出去：{{ notifyTest.detail }}</template>
            </span>
            <span v-else class="hint">会先保存，再发一条示例信息过去。</span>
          </div>
        </section>

        <section class="block">
          <h3>免打扰</h3>
          <div class="quiet">
            <label class="field inline">
              <span class="lbl">从</span>
              <input v-model="quietStart" class="input" type="time" />
            </label>
            <label class="field inline">
              <span class="lbl">到</span>
              <input v-model="quietEnd" class="input" type="time" />
            </label>
          </div>
          <span class="hint">
            落在这个时段的提醒会挪到结束之后再发，不会被丢掉。
          </span>
        </section>

        <section class="block">
          <h3>判断严格程度</h3>
          <label class="field">
            <span class="lbl">
              置信度门槛
              <span class="num">{{ Number(threshold).toFixed(2) }}</span>
            </span>
            <input
              v-model="threshold"
              class="range"
              type="range"
              min="0"
              max="1"
              step="0.05"
            />
            <span class="hint">
              低于这个分数的抽取结果进「待确认」，等你点一下再算任务。调高更谨慎，调低更省事。
            </span>
          </label>

          <label class="check">
            <input v-model="autoConfirm" type="checkbox" />
            <span>
              自动确认
              <span class="hint">
                打开后不再有「待确认」，AI 抽到就直接当任务。演示时省一步，日常不建议。
              </span>
            </span>
          </label>
        </section>

        <section class="block">
          <h3>
            任务搬家 <span class="tag">全局</span>
          </h3>
          <p class="hint block-hint">
            把任务导成一个 JSON 文件，换台电脑再导回来。只带任务本身，群设置和推送
            设置不跟着走。
          </p>

          <div class="testrow">
            <button
              class="btn"
              type="button"
              :disabled="transferBusy"
              @click="requestExport"
            >
              导出任务
            </button>
            <button
              class="btn"
              type="button"
              :disabled="transferBusy"
              @click="pickFile"
            >
              {{ transferBusy ? '导入中…' : '导入任务' }}
            </button>
            <!-- Hidden because the native file input cannot be styled to match,
                 and the button above is what the student is looking for. -->
            <input
              ref="fileInput"
              class="hidden-file"
              type="file"
              accept="application/json,.json"
              @change="onFilePicked"
            />
            <span class="hint">导出的是全部群的任务，包括已完成的。</span>
          </div>

          <label class="check">
            <input v-model="importHere" type="checkbox" />
            <span>
              全部导入到当前群
              <span class="hint">
                两台电脑的群号不一样时勾上，否则任务会落到一个看板上没有的群里。
              </span>
            </span>
          </label>

          <label class="check">
            <input v-model="importOverwrite" type="checkbox" />
            <span>
              覆盖已有的同一个任务
              <span class="hint">
                默认跳过重复的。勾上则用文件里的内容改写现有任务，用来同步修改。
              </span>
            </span>
          </label>
        </section>

        <p
          v-if="transferResult"
          class="hint transfer-result"
          :class="{ bad: !transferResult.ok }"
          role="status"
        >
          {{ transferResult.text }}
        </p>

        <footer class="foot">
          <span v-if="dirty" class="dirty">有未保存的改动</span>
          <span v-else class="dirty quiet">没有改动</span>
          <button class="btn btn-quiet" type="button" @click="$emit('close')">
            关闭
          </button>
          <button class="btn btn-primary" type="submit" :disabled="!dirty || saving">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </footer>
      </form>
    </div>
  </div>
</template>

<style scoped>
/* Same dialog chrome as TaskEditor: two modals that look different would read as
 * two different products. Wider, because the lead-time chips need the room. */
.scrim {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: var(--sp-4);
  background: rgba(31, 28, 23, 0.34);
  animation: fade var(--duration) var(--ease);
}
@keyframes fade { from { opacity: 0 } }

.sheet {
  width: min(600px, 100%);
  max-height: min(88vh, 820px);
  display: flex;
  flex-direction: column;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  animation: rise var(--duration) var(--ease);
}
@keyframes rise { from { transform: translateY(8px); opacity: 0 } }

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-4) var(--sp-5);
  border-bottom: 1px solid var(--rule);
}
.head h2 { margin: 0; font-size: var(--text-lg); font-weight: 600; }
.who { margin: 2px 0 0; font-size: var(--text-xs); color: var(--ink-faint); }

.close {
  font: inherit;
  width: 28px; height: 28px;
  color: var(--ink-faint);
  background: none;
  border: 1px solid var(--rule);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.close:hover { color: var(--ink); background: var(--paper-sunken); }

.form {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: var(--sp-5);
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
}

.block { display: flex; flex-direction: column; gap: var(--sp-3); }
.block h3 {
  margin: 0;
  padding-bottom: var(--sp-2);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink);
  border-bottom: 1px solid var(--rule);
}
.block-hint { margin: 0; }

.field { display: flex; flex-direction: column; gap: var(--sp-2); }
.field.inline { flex-direction: row; align-items: center; gap: var(--sp-2); }
.lbl {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  flex-wrap: wrap;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink-muted);
}
.num {
  font-family: var(--font-numeric);
  font-variant-numeric: tabular-nums;
  font-weight: 400;
  color: var(--accent);
}

.input {
  font: inherit;
  font-size: var(--text-base);
  padding: var(--sp-2) var(--sp-3);
  color: var(--ink);
  background: var(--paper-raised);
  border: 1.5px solid var(--rule-strong);
  border-radius: var(--radius-sm);
  transition: border-color var(--duration) var(--ease);
}
.input:focus { outline: none; border-color: var(--accent); }
input[type='time'] {
  font-family: var(--font-numeric);
  font-variant-numeric: tabular-nums;
}

.range { accent-color: var(--accent); }

.hint {
  font-size: var(--text-xs);
  font-weight: 400;
  color: var(--ink-faint);
  line-height: var(--leading-normal);
}
.warn {
  margin: 0;
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
  color: var(--accent-strong);
  background: var(--accent-wash);
  border-radius: var(--radius-sm);
}

.check {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-2);
  font-size: var(--text-sm);
  cursor: pointer;
}
.check input { margin-top: 3px; }
.check span { display: flex; flex-direction: column; gap: 2px; }

/* Label on the left, chips wrapping on the right: five rows of chips read as one
 * table rather than five separate controls. */
.leadrow {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
}
.leadname {
  flex: 0 0 3.2em;
  font-size: var(--text-sm);
  color: var(--ink-muted);
}
.chips { display: flex; flex-wrap: wrap; gap: var(--sp-2); }

.chip {
  font: inherit;
  font-size: var(--text-xs);
  padding: 3px var(--sp-2);
  color: var(--ink-faint);
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: 999px;
  cursor: pointer;
  transition: color var(--duration) var(--ease), border-color var(--duration) var(--ease),
    background var(--duration) var(--ease);
}
.chip:hover { color: var(--ink); border-color: var(--ink-faint); }
.chip.on {
  color: #fff;
  background: var(--accent);
  border-color: var(--accent);
}

.quiet { display: flex; align-items: center; gap: var(--sp-4); flex-wrap: wrap; }

/* Sticky for the same reason as TaskEditor's: this form scrolls, and a 保存 below
 * the fold reads as a dialog with no way to commit. */
.foot {
  position: sticky;
  bottom: calc(-1 * var(--sp-5));
  z-index: 1;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin: 0 calc(-1 * var(--sp-5)) calc(-1 * var(--sp-5));
  padding: var(--sp-4) var(--sp-5);
  background: var(--paper);
  border-top: 1px solid var(--rule);
}
.dirty { margin-right: auto; font-size: var(--text-xs); color: var(--accent); }
.dirty.quiet { color: var(--ink-faint); }

.btn {
  font: inherit;
  font-size: var(--text-sm);
  padding: var(--sp-2) var(--sp-4);
  color: var(--ink);
  background: var(--paper-raised);
  border: 1px solid var(--rule-strong);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--duration) var(--ease), border-color var(--duration) var(--ease);
}
.btn:hover:not(:disabled) { background: var(--paper-sunken); border-color: var(--ink-faint); }
.btn:disabled { opacity: 0.45; cursor: default; }
.btn-primary { color: #fff; background: var(--accent); border-color: var(--accent); }
.btn-primary:hover:not(:disabled) { background: var(--accent-strong); border-color: var(--accent-strong); }
.btn-quiet { color: var(--ink-faint); border-color: var(--rule); }
/* Outlined rather than filled: a filled red button next to a filled red 保存 in
 * the footer makes the destructive one look like the expected action. */
.btn-danger { color: var(--accent); border-color: var(--accent); }
.btn-danger:hover:not(:disabled) { color: #fff; background: var(--accent); }

/* Marks the one section that is not per-group. Without it a student would
 * reasonably read 消息发到哪 as a setting for the group named in the header. */
.tag {
  padding: 1px var(--sp-2);
  font-size: var(--text-xs);
  font-weight: 400;
  color: var(--ink-faint);
  background: var(--paper-sunken);
  border: 1px solid var(--rule);
  border-radius: 999px;
  vertical-align: 2px;
}

/* Two cards rather than radio inputs: the choice carries a consequence (who
 * else sees the message) and that consequence needs room to be written down. */
.modes { display: flex; gap: var(--sp-2); }
.mode {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font: inherit;
  font-size: var(--text-sm);
  text-align: left;
  padding: var(--sp-2) var(--sp-3);
  color: var(--ink-muted);
  background: var(--paper-raised);
  border: 1.5px solid var(--rule);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: color var(--duration) var(--ease), border-color var(--duration) var(--ease);
}
.mode:hover { border-color: var(--ink-faint); }
.mode.on { color: var(--ink); border-color: var(--accent); background: var(--accent-wash); }

.target { margin: 0; font-size: var(--text-sm); color: var(--ink-muted); }
.target strong { color: var(--ink); }

/* A disabled switch with no reason next to it reads as broken. The reason is in
 * the hint; this only dims the label so the two agree. */
.check.off { cursor: default; }
.check.off > span { opacity: 0.6; }

.testrow { display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; }
.testrow .hint { flex: 1; min-width: 10em; }
.hint.bad { color: var(--accent); }

/* The real input is kept in the DOM rather than replaced, so the click on the
 * styled button still opens the OS file dialog. `display: none` would work in
 * every browser tested but drops it out of the accessibility tree. */
.hidden-file {
  position: absolute;
  width: 1px; height: 1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}

/* Separated from the switches above by a rule: everything else in this panel is
 * reversible, and this is the one control that is not. */
.danger {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex-wrap: wrap;
  padding-top: var(--sp-3);
  border-top: 1px dashed var(--rule);
}
.danger .hint { flex: 1; min-width: 12em; }

@media (max-width: 560px) {
  .sheet { max-height: 94vh; }
  .leadrow { flex-direction: column; align-items: stretch; gap: var(--sp-2); }
  .modes { flex-direction: column; }
  .foot { flex-wrap: wrap; }
  .dirty { width: 100%; margin-bottom: var(--sp-2); }
}
</style>
