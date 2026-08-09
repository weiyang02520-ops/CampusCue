<script setup>
/**
 * The board.
 *
 * Grouping is by urgency rather than by course or type, because the question a
 * student opens this to answer is "what do I have to do now", not "what does
 * this course want". Type is available as a tint on each card, which is enough
 * to scan by without making it the primary axis.
 *
 * The live-arrival behaviour is the demo's centrepiece: a message is posted in
 * the group and roughly two seconds later the card appears on screen, unprompted.
 * New cards get a brief highlight so the eye is drawn to the change instead of
 * having to re-scan the list.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import ReminderList from './components/ReminderList.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import SetupPanel from './components/SetupPanel.vue'
import SourcePicker from './components/SourcePicker.vue'
import TaskCard from './components/TaskCard.vue'
import TaskEditor from './components/TaskEditor.vue'
import TracePanel from './components/TracePanel.vue'
import {
  connectionLabel,
  groupTasks,
  mergeTask,
  restoreTask,
  streamOpened,
} from './boardState.js'
import { requestJson } from './http.js'

const API = '/api/v1/campus'
const MAX_TASK_TRANSFER_BYTES = 10 * 1024 * 1024
const MAX_BACKUP_BYTES = 50 * 1024 * 1024

const tasks = ref([])
const stats = ref(null)
const loading = ref(true)
const error = ref(null)
const connected = ref(false)
const disconnectedAt = ref(null)
const arrivals = ref(new Set())
const detail = ref(null)
const detailLoading = ref(false)
const showDone = ref(false)

const sources = ref([])
/** Empty until /default-source answers. Requests before that omit `umo` and get
 *  the server's own default, so the board is never briefly pointed at the wrong
 *  group while the picker is still loading. */
const umo = ref('')

const editing = ref(null)
const saving = ref(false)

const reminders = ref([])
const remindersLoading = ref(false)

const settingsOpen = ref(false)
const profile = ref(null)
const settingsSaving = ref(false)

/** Where detections go. Global rather than per group, so unlike `profile` it is
 *  not dropped when the board switches groups -- only refetched when the dialog
 *  opens, which is the only place it is shown. */
const notify = ref(null)
const notifyTest = ref(null)
const notifyTesting = ref(false)

/** Result of the last 导出/导入, as `{ ok, text }`. Shown in the dialog rather
 *  than as a toast: an import reports counts the student has to read against the
 *  board ("3 条新的，2 条已经在这里了"), and a banner that fades cannot be reread. */
const transferResult = ref(null)
const transferBusy = ref(false)

/** The 接入 dialog. Opens itself on a board that has never seen a message and has
 *  no QQ attached -- that is a fresh install, and the first useful screen there is
 *  the one that gets it online, not an empty task list. */
const setupOpen = ref(false)
/** Whether a QQ account is attached, as of the last check. Read once on load
 *  rather than polled: the panel polls while it is open, and the header only
 *  needs to know whether to mark the button. */
const linked = ref(true)

/** Ticks the countdowns. 30s is frequent enough that "3小时" never looks stale,
 *  and cheap enough to leave running on a projector for an hour. */
const now = ref(Date.now())
let clock = null
let stream = null
let hasOpenedStream = false

async function api(path, options = {}) {
  return requestJson(`${API}${path}`, options)
}

/** `&umo=` only once the picker has resolved. See the ref's comment. */
function scope() {
  return umo.value ? `&umo=${encodeURIComponent(umo.value)}` : ''
}

async function load() {
  try {
    // Dismissed tasks come back with the done ones: "不是任务" is the judgement
    // most worth reversing, and a card the student can never see again is a
    // card they cannot undo.
    const statuses = showDone.value
      ? 'active,pending_confirm,done,dismissed'
      : 'active,pending_confirm'
    const [taskList, summary] = await Promise.all([
      api(`/tasks?status=${statuses}${scope()}`),
      api(`/stats?${scope().slice(1)}`),
    ])
    tasks.value = taskList
    stats.value = summary
    error.value = null
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

/** Resolve which board to show, and what else is available.
 *
 * The default comes from the server because it is set by CAMPUSCUE_DEMO_UMO --
 * hard-coding it here would leave the board empty on exactly the machine a demo
 * runs on.
 */
async function loadSources() {
  try {
    const [list, fallback] = await Promise.all([
      api('/sources'),
      api('/default-source'),
    ])
    sources.value = list
    const fallbackUmo = fallback?.umo || ''
    const currentStillExists = list.some((source) => source.umo === umo.value)
    if (!umo.value || !currentStillExists) {
      umo.value =
        list.find((source) => source.umo === fallbackUmo)?.umo ||
        list[0]?.umo ||
        fallbackUmo
    }
  } catch {
    // A failed picker must not blank the board: without a umo every request
    // falls back to the server's default, which is the single-group case.
  }
}

async function loadReminders() {
  remindersLoading.value = true
  try {
    reminders.value = await api(`/reminders?${scope().slice(1)}`)
  } catch (err) {
    error.value = err.message
  } finally {
    remindersLoading.value = false
  }
}

/** The row in `sources` for the group currently on screen.
 *
 * Falls back to a synthetic entry so the settings dialog opens on a fresh
 * install too: on a machine where nothing has been extracted yet there is no
 * source row, and naming the group is exactly what you would want to do first.
 */
const currentSource = computed(
  () =>
    sources.value.find((s) => s.umo === umo.value) || {
      umo: umo.value,
      label: umo.value || '当前群',
      course_name: null,
      display_name: null,
      source_type: 'course',
      enabled: true,
    },
)

/** Preferences are fetched on open rather than on load: the board does not need
 *  them to render, and reading them materialises a row. */
async function openSettings() {
  settingsOpen.value = true
  // Stale from a previous visit: a green 已发到 from five minutes ago next to
  // switches that have since changed reads as a fresh confirmation.
  notifyTest.value = null
  transferResult.value = null
  try {
    // Together, because they render in one dialog: fetched in sequence, the
    // delivery section would pop in after the student is already reading.
    const [prefs, delivery] = await Promise.all([
      api(`/profile?${scope().slice(1)}`),
      api('/notify'),
    ])
    profile.value = prefs
    notify.value = delivery
  } catch (err) {
    error.value = err.message
  }
}

async function saveSettings({ source, profile: prefs, notify: delivery }) {
  settingsSaving.value = true
  try {
    if (source) {
      const saved = await api(`/sources/${encodeURIComponent(umo.value)}`, {
        method: 'PATCH',
        body: JSON.stringify(source),
      })
      sources.value = sources.value.some((s) => s.umo === saved.umo)
        ? sources.value.map((s) => (s.umo === saved.umo ? saved : s))
        : [...sources.value, saved]
    }
    if (prefs) {
      profile.value = await api(`/profile?${scope().slice(1)}`, {
        method: 'PATCH',
        body: JSON.stringify(prefs),
      })
      // The server resyncs the whole schedule on a lead-time change, so
      // whatever the reminder panel is showing is now wrong.
      if (prefs.lead_minutes || prefs.quiet_hours) loadReminders()
    }
    if (delivery) {
      notify.value = await api('/notify', {
        method: 'PATCH',
        body: JSON.stringify(delivery),
      })
      // Turning the deadline channel off leaves no alarms; turning it back on
      // resyncs the whole table server-side. Either way the panel is stale.
      if ('deadline_reminders' in delivery) loadReminders()
    }
    settingsOpen.value = false
  } catch (err) {
    error.value = err.message
  } finally {
    settingsSaving.value = false
  }
}

/** Send one sample detection through the real delivery path.
 *
 * Saves the on-screen changes first: testing the stored settings while the
 * student is looking at edited ones would report on something they cannot see,
 * and a green result for the wrong target is worse than no result.
 */
async function testNotify({ pending }) {
  notifyTesting.value = true
  notifyTest.value = null
  try {
    if (pending) {
      notify.value = await api('/notify', {
        method: 'PATCH',
        body: JSON.stringify(pending),
      })
      if ('deadline_reminders' in pending) loadReminders()
    }
    notifyTest.value = await api('/notify/test', { method: 'POST' })
  } catch (err) {
    error.value = err.message
  } finally {
    notifyTesting.value = false
  }
}

/** Drop a watched group and everything extracted from it.
 *
 * Confirmed in the browser rather than with a second panel: this exists to clear
 * fixture groups out of a demo database, and it is irreversible. The board is
 * repointed before reloading because the group it was showing no longer exists.
 */
async function deleteSource(source) {
  const target = source?.umo
  if (!target) return
  const label = source.label || target
  const message =
    `删除「${label}」？\n\n` +
    '它抽出来的任务和已排的提醒会一起删掉，不能撤销。'
  if (!window.confirm(message)) return
  settingsSaving.value = true
  try {
    await api(`/sources/${encodeURIComponent(target)}`, { method: 'DELETE' })
    settingsOpen.value = false
    profile.value = null
    sources.value = sources.value.filter((s) => s.umo !== target)
    if (umo.value === target) {
      // The watcher on `umo` reloads the board, but only if the value actually
      // changes -- so fall back explicitly when this was the last group.
      const next = sources.value[0]?.umo || ''
      if (next) umo.value = next
      else {
        umo.value = ''
        await Promise.all([load(), loadReminders()])
      }
    } else {
      await load()
    }
    // The picker's counts and the delivery candidates both listed the group.
    notify.value = null
  } catch (err) {
    error.value = err.message
  } finally {
    settingsSaving.value = false
  }
}

/** Download every task as one JSON file.
 *
 * Fetched with `fetch` directly instead of pointing a link at the endpoint: the
 * board may be served behind the dashboard's auth, and a plain navigation would
 * drop the headers `api()` sets and hand back a login page named like a backup.
 */
async function exportTasks() {
  transferBusy.value = true
  transferResult.value = null
  try {
    const body = await api('/export')
    const stamp = new Date().toISOString().slice(0, 10)
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(body, null, 2)], { type: 'application/json' }),
    )
    const a = document.createElement('a')
    a.href = url
    a.download = `课讯任务-${stamp}.json`
    a.click()
    URL.revokeObjectURL(url)
    const groups = body.umos?.length || 0
    transferResult.value = {
      ok: true,
      text: `导出了 ${body.count} 条任务（${groups} 个群），已下载。`,
    }
  } catch (err) {
    transferResult.value = { ok: false, text: `导出失败：${err.message}` }
  } finally {
    transferBusy.value = false
  }
}

/** Read a picked file and hand its tasks to the server.
 *
 * Parsed here first so the common mistake -- picking a file that is not a
 * CampusCue export -- fails with a sentence about that file instead of a 422
 * from the API. Everything the board shows is reloaded afterwards: an import
 * writes tasks and re-plans reminders, so the list, the picker's counts and the
 * reminder panel are all stale at once.
 */
async function importTasks({ file, overwrite, umo: target }) {
  transferBusy.value = true
  transferResult.value = null
  try {
    if (file.size > MAX_TASK_TRANSFER_BYTES) {
      throw new Error('任务文件超过 10MB，请确认没有选错文件')
    }
    let doc
    try {
      doc = JSON.parse(await file.text())
    } catch {
      throw new Error('这个文件不是 JSON，选一个课讯导出的文件')
    }
    const report = await api('/import', {
      method: 'POST',
      body: JSON.stringify({ ...doc, umo: target || null, overwrite }),
    })
    const parts = [`新增 ${report.created} 条`]
    if (report.updated) parts.push(`更新 ${report.updated} 条`)
    if (report.skipped) parts.push(`跳过 ${report.skipped} 条`)
    if (report.reminders_planned) parts.push(`排了 ${report.reminders_planned} 个提醒`)
    transferResult.value = {
      ok: true,
      text: report.detail || `${parts.join('，')}。`,
    }
    await Promise.all([loadSources(), load(), loadReminders()])
  } catch (err) {
    transferResult.value = { ok: false, text: `导入失败：${err.message}` }
  } finally {
    transferBusy.value = false
  }
}

function downloadJson(body, filename) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(body, null, 2)], { type: 'application/json' }),
  )
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

async function exportBackup() {
  transferBusy.value = true
  transferResult.value = null
  try {
    const body = await api('/backup')
    const stamp = new Date().toISOString().slice(0, 10)
    downloadJson(body, `课讯完整备份-${stamp}.json`)
    transferResult.value = {
      ok: true,
      text: `完整备份已下载：${body.tasks?.length || 0} 条任务，${body.sources?.length || 0} 个来源。`,
    }
  } catch (err) {
    transferResult.value = { ok: false, text: `备份失败：${err.message}` }
  } finally {
    transferBusy.value = false
  }
}

async function restoreBackup({ file }) {
  transferBusy.value = true
  transferResult.value = null
  try {
    if (file.size > MAX_BACKUP_BYTES) {
      throw new Error('备份文件超过 50MB，请确认没有选错文件')
    }
    let doc
    try {
      doc = JSON.parse(await file.text())
    } catch {
      throw new Error('这个文件不是 JSON，选一个课讯完整备份')
    }
    const tasksCount = Array.isArray(doc.tasks) ? doc.tasks.length : 0
    const sourcesCount = Array.isArray(doc.sources) ? doc.sources.length : 0
    const confirmed = window.confirm(
      `恢复完整备份？\n\n当前课讯数据会被替换为文件中的 ${tasksCount} 条任务、${sourcesCount} 个来源。此操作不能撤销。`,
    )
    if (!confirmed) {
      transferResult.value = { ok: false, text: '已取消恢复，当前数据没有变化。' }
      return
    }
    const report = await api('/restore', {
      method: 'POST',
      body: JSON.stringify({ ...doc, confirm_replace: true }),
    })
    await loadSources()
    await Promise.all([load(), loadReminders()])
    profile.value = null
    notify.value = null
    transferResult.value = {
      ok: true,
      text:
        report.detail ||
        `恢复完成：${report.tasks} 条任务、${report.sources} 个来源、${report.extractions} 条溯源记录。`,
    }
  } catch (err) {
    transferResult.value = { ok: false, text: `恢复失败：${err.message}` }
  } finally {
    transferBusy.value = false
  }
}

/** Open the editor on a blank task.
 *
 * Not every affair arrives in a group chat -- a lecturer says it out loud, or the
 * student learns it from a poster. Without this the board can only ever repair
 * what the extractor found, which makes it a viewer of the AI rather than the
 * student's actual list.
 */
function startCreate() {
  editing.value = {
    title: '',
    task_type: 'notice',
    deadline: null,
    location: null,
    items: [],
    detail: null,
  }
}

async function saveEdit({ task, fields, create }) {
  if (saving.value) return  // double-submit guard: a fast double-click must not
                            // post two identical tasks
  saving.value = true
  try {
    // Creating posts the whole draft; editing patches only the diff. The board
    // scopes the new task to the group it is currently showing, so a task typed
    // in while filtered to 软件工程 belongs to 软件工程.
    const saved = create
      ? await api(`/tasks?${scope().slice(1)}`, {
          method: 'POST',
          body: JSON.stringify(fields),
        })
      : await api(`/tasks/${task.task_id}`, {
          method: 'PATCH',
          body: JSON.stringify(fields),
        })
    upsert(saved)
    editing.value = null
    // A deadline that moved -- or arrived -- reshuffles the alarms, so the
    // panel's contents are stale the moment this returns.
    if (create || 'deadline' in fields) loadReminders()
    if (create) loadSources()
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

watch(umo, (next, previous) => {
  // The watcher only fires on *change*; the first assignment (from
  // loadSources resolving the default) is handled there instead, because the
  // requests issued before it were scoped to the server's demo default.
  if (!previous || next === previous) return
  loading.value = true
  tasks.value = []
  load()
  // Unconditional: alarms are per group, so the ones in hand are the previous
  // group's regardless of whether the panel has been opened.
  loadReminders()
  // Preferences are per group, so the ones in hand belong to the group that was
  // just left. Dropping them rather than refetching: the dialog is closed.
  profile.value = null
  settingsOpen.value = false
})

/** Mark a card as newly arrived, then let the highlight decay. */
function flash(taskId) {
  arrivals.value = new Set(arrivals.value).add(taskId)
  setTimeout(() => {
    const next = new Set(arrivals.value)
    next.delete(taskId)
    arrivals.value = next
  }, 4000)
}

/** True when a task belongs on the board as currently filtered.
 *
 * The SSE stream is global -- one hub for the whole process -- so once the board
 * can be scoped to one group, every arriving event has to be checked. Without
 * this a message in another group would make a card appear under a heading that
 * says it is showing something else.
 */
function inScope(task) {
  return !umo.value || task.umo === umo.value
}

function upsert(task) {
  // A full TaskOut is required: some hub events (reminder_fired) carry only
  // {task_id, label, delivered} and must never be upserted -- they would
  // replace a real card with a three-field husk.
  const merged = mergeTask(tasks.value, task, umo.value)
  if (merged.tasks === tasks.value) return
  tasks.value = merged.tasks
  if (merged.inserted) {
    // Newest first regardless of deadline: the point of the animation is that
    // something just happened, so it must land where the eye already is.
    flash(task.task_id)
  }
}

function connect() {
  stream = new EventSource(`${API}/stream`)
  stream.onopen = () => {
    const opened = streamOpened(hasOpenedStream)
    hasOpenedStream = opened.hasOpened
    connected.value = true
    disconnectedAt.value = null
    // First open needs no refetch -- load() already ran. A *reconnect* means
    // events fired while the socket was down were dropped (the hub drops
    // oldest first and the client is expected to refetch on reconnect), so
    // pull the whole board and the reminder panel back into view.
    if (opened.shouldResync) {
      load()
      loadReminders()
      loadSources()
    }
  }
  stream.onerror = () => {
    // EventSource reconnects on its own; reflect the gap rather than tearing down.
    connected.value = false
    if (!disconnectedAt.value) disconnectedAt.value = Date.now()
  }
  stream.onmessage = (event) => {
    let payload
    try {
      payload = JSON.parse(event.data)
    } catch {
      return
    }
    const { event: kind, data } = payload
    if (!data?.task_id) return

    // A reminder fired is not a task update: the payload is
    // {task_id, label, delivered}, not a TaskOut. The panel's list of alarms
    // is what changed, so refresh that and leave the cards alone.
    if (kind === 'reminder_fired') {
      loadReminders()
      return
    }

    if (!inScope(data)) {
      // Another group's traffic. The counts still move, so the picker is
      // refreshed and the badge on that group grows even while it is not shown.
      loadSources()
      return
    }

    if (kind === 'task_completed' || kind === 'task_dismissed') {
      if (!showDone.value) {
        tasks.value = tasks.value.filter((t) => t.task_id !== data.task_id)
      } else {
        upsert(data)
      }
    } else {
      upsert(data)
    }
    // Counters come from the server so they cannot drift from the database.
    api(`/stats?${scope().slice(1)}`)
      .then((s) => { stats.value = s })
      .catch(() => {})
    if (kind === 'task_created') loadSources()
  }
}

async function act(task, action) {
  // Optimistic: the click should feel instant. The server's own TaskOut is
  // the source of truth afterwards -- relying on the SSE echo alone leaves
  // the card stuck whenever the stream is down (shown as 连接中断).
  const previous = tasks.value
  if (action === 'complete' || action === 'dismiss') {
    if (!showDone.value) {
      tasks.value = tasks.value.filter((t) => t.task_id !== task.task_id)
    }
  } else if (action === 'reopen') {
    // Reopening only ever happens from the 已完成 group, which is only visible
    // when showDone is on, so the card stays put and just changes status.
    tasks.value = tasks.value.map((t) =>
      t.task_id === task.task_id ? { ...t, status: 'active' } : t,
    )
  }
  try {
    const saved = await api(`/tasks/${task.task_id}/${action}`, { method: 'POST' })
    // The optimistic pass above already removed the card when the done group
    // is hidden; upserting the returned task would re-insert it. With 显示已
    // 完成 on (or for reopen, which only exists there) the card is still on
    // screen and just needs its fresh state.
    if (action === 'reopen' || showDone.value) {
      upsert(saved)
    }
    // Every one of these moves alarms: complete and dismiss cancel them, reopen
    // schedules them again. The panel's count is on screen while collapsed, so
    // "stale but hidden" is not a state it has.
    loadReminders()
  } catch (err) {
    // Roll back only the card this action touched, not the whole list: a
    // wholesale restore would also undo an SSE update that arrived mid-flight.
    tasks.value = restoreTask(tasks.value, previous, task.task_id)
    error.value = err.message
  }
}

async function openTrace(task) {
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await api(`/tasks/${task.task_id}`)
  } catch (err) {
    error.value = err.message
  } finally {
    detailLoading.value = false
  }
}

const pending = computed(() =>
  tasks.value.filter((t) => t.status === 'pending_confirm'),
)

/** Urgency buckets, in the order a student cares about them. */
const groups = computed(() => groupTasks(tasks.value, now.value))
const liveLabel = computed(() =>
  connectionLabel(connected.value, disconnectedAt.value, now.value),
)
const prolongedOffline = computed(
  () =>
    !connected.value &&
    disconnectedAt.value &&
    now.value - disconnectedAt.value >= 60_000,
)

const filteredPercent = computed(() => {
  const ratio = stats.value?.l1_filtered_ratio
  return ratio ? Math.round(ratio * 100) : null
})

/** Is anything actually connected?
 *
 * Defaults to "yes" on failure. Falsely marking the 接入 button on a working
 * install -- or worse, opening the dialog over a board that is fine -- is more
 * annoying than missing the nudge on a broken one.
 */
async function checkLink() {
  try {
    const status = await api('/setup/status')
    linked.value = Boolean(status.link?.connected)
    // A fresh install means no QQ attached, no watched groups, *and* nothing on
    // the board. The setup/status endpoint lists only real source rows, while
    // the board's /sources endpoint synthesises the demo session when no real
    // group exists -- so a board showing tasks must not be buried under the
    // setup dialog just because QQ is not connected yet.
    if (!linked.value && !status.sources?.length && !tasks.value.length) {
      setupOpen.value = true
    }
  } catch {
    // Leave `linked` optimistic; see the doc comment.
  }
}

function handleOffline() {
  connected.value = false
  if (!disconnectedAt.value) disconnectedAt.value = Date.now()
}

async function handleOnline() {
  error.value = null
  await Promise.allSettled([loadSources(), load(), loadReminders(), checkLink()])
}

onMounted(async () => {
  // Resolve the real group before any scoped request. Otherwise the first paint
  // can show the demo board and decide this is a fresh install while the watched
  // group's tasks are still in flight.
  await loadSources()
  await Promise.all([load(), loadReminders()])
  await checkLink()
  // Fetched up front even though the panel is collapsed: its bar shows the count
  // and the next firing time, and with an empty list that bar reads 暂无 -- i.e.
  // "nothing will remind you", which is the opposite of the truth and the one
  // claim the product cannot afford to get wrong on first paint.
  connect()
  clock = setInterval(() => { now.value = Date.now() }, 30_000)
  window.addEventListener('offline', handleOffline)
  window.addEventListener('online', handleOnline)
})

onUnmounted(() => {
  if (clock) clearInterval(clock)
  if (stream) stream.close()
  window.removeEventListener('offline', handleOffline)
  window.removeEventListener('online', handleOnline)
})
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <h1>课讯</h1>
        <span class="tagline">校园通知，自动变成待办</span>
      </div>

      <div class="controls">
        <SourcePicker v-model="umo" :sources="sources" />
        <button class="new" type="button" @click="startCreate">
          <span aria-hidden="true">＋</span> 新建
        </button>
        <button class="new quiet" type="button" title="群设置" @click="openSettings">
          <span aria-hidden="true">⚙</span> 设置
        </button>
        <!-- Marked when nothing is attached: on a machine with no QQ connected
             this is the only button on the header that leads anywhere. -->
        <button
          class="new quiet"
          :class="{ nudge: !linked }"
          type="button"
          title="接入 QQ 与自检"
          @click="setupOpen = true"
        >
          <span aria-hidden="true">⚡</span> 接入
        </button>
        <div class="live" :class="{ on: connected, stalled: prolongedOffline }">
          <span class="pulse" aria-hidden="true" />
          {{ liveLabel }}
        </div>
      </div>
    </header>

    <section v-if="stats" class="metrics" aria-label="概览">
      <div class="metric">
        <span class="n">{{ stats.due_today }}</span>
        <span class="l">今天到期</span>
      </div>
      <div class="metric">
        <span class="n">{{ stats.due_this_week }}</span>
        <span class="l">七天内</span>
      </div>
      <div class="metric" :class="{ warn: stats.overdue > 0 }">
        <span class="n">{{ stats.overdue }}</span>
        <span class="l">已逾期</span>
      </div>
      <div class="metric spacer" />
      <!-- Not vanity: this is the measured share of group traffic that never
           reached a model, which is the cost argument in one number. -->
      <div v-if="filteredPercent !== null" class="metric quiet">
        <span class="n">{{ filteredPercent }}%</span>
        <span class="l">消息被本地规则挡下</span>
      </div>
      <div class="metric quiet">
        <span class="n">{{ stats.messages_seen }}</span>
        <span class="l">已读群消息</span>
      </div>
    </section>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <!-- Low-confidence extractions, surfaced above the board so the decision is
         one click and never blocks the rest of the list. -->
    <section v-if="pending.length" class="confirm" aria-label="待确认">
      <h2>
        待确认
        <span class="hint">系统不确定这些是不是任务，你说了算</span>
      </h2>
      <div class="grid">
        <TaskCard
          v-for="task in pending"
          :key="task.task_id"
          :task="task"
          :now="now"
          :class="{ arrived: arrivals.has(task.task_id) }"
          @confirm="act($event, 'confirm')"
          @dismiss="act($event, 'dismiss')"
          @trace="openTrace"
          @edit="editing = $event"
        />
      </div>
    </section>

    <ReminderList
      :reminders="reminders"
      :loading="remindersLoading"
      @refresh="loadReminders"
    />

    <main class="board">
      <div v-if="loading" class="state">读取中…</div>

      <div v-else-if="!groups.length && !pending.length" class="state empty">
        <p class="empty-title">还没有任务</p>
        <p class="empty-body">
          课讯正在监听群消息。老师发出作业、考试或比赛通知时，任务会自动出现在这里。
        </p>
        <p class="empty-actions">
          <button class="new" type="button" @click="startCreate">
            <span aria-hidden="true">＋</span> 手动添加一个
          </button>
        </p>
        <p class="empty-actions">
          <button class="new quiet" type="button" @click="setupOpen = true">
            <span aria-hidden="true">⚡</span> 接入 QQ 群
          </button>
        </p>
        <p class="empty-hint">
          也可以运行 <code>python -m campuscue.replay --all</code> 灌入示例消息。
        </p>
      </div>

      <section v-for="group in groups" :key="group.key" class="group">
        <h2>
          {{ group.label }}
          <span class="count">{{ group.items.length }}</span>
        </h2>
        <div class="grid">
          <TaskCard
            v-for="task in group.items"
            :key="task.task_id"
            :task="task"
            :now="now"
            :class="{ arrived: arrivals.has(task.task_id) }"
            @complete="act($event, 'complete')"
            @dismiss="act($event, 'dismiss')"
            @reopen="act($event, 'reopen')"
            @trace="openTrace"
            @edit="editing = $event"
          />
        </div>
      </section>

      <footer class="boardfoot">
        <label>
          <input v-model="showDone" type="checkbox" @change="load" />
          显示已完成 / 已忽略
        </label>
      </footer>
    </main>

    <TracePanel
      :detail="detail"
      :loading="detailLoading"
      @close="detail = null"
    />

    <TaskEditor
      :task="editing"
      :saving="saving"
      @save="saveEdit"
      @close="editing = null"
    />

    <SetupPanel
      :open="setupOpen"
      @changed="loadSources(); checkLink()"
      @close="setupOpen = false"
    />

    <SettingsPanel
      :open="settingsOpen"
      :source="currentSource"
      :profile="profile"
      :notify="notify"
      :notify-test="notifyTest"
      :testing="notifyTesting"
      :saving="settingsSaving"
      :transfer-result="transferResult"
      :transfer-busy="transferBusy"
      @save="saveSettings"
      @test-notify="testNotify"
      @delete-source="deleteSource"
      @export-tasks="exportTasks"
      @import-tasks="importTasks"
      @export-backup="exportBackup"
      @restore-backup="restoreBackup"
      @close="settingsOpen = false"
    />
  </div>
</template>

<style scoped>
.app {
  max-width: 1180px;
  margin: 0 auto;
  padding: var(--sp-5) var(--sp-5) var(--sp-7);
}

.topbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-4);
  flex-wrap: wrap;
  padding-bottom: var(--sp-4);
  border-bottom: 1.5px solid var(--rule-strong);
}

.brand { display: flex; align-items: baseline; gap: var(--sp-3); flex-wrap: wrap; }
.brand h1 {
  margin: 0;
  font-size: var(--text-2xl);
  font-weight: 700;
  letter-spacing: -0.01em;
}
.tagline { font-size: var(--text-sm); color: var(--ink-faint); }

/* Picker and live indicator share the right side of the header. Column-reversed
 * on narrow screens so the indicator stays on the same line as the title. */
.controls {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  flex-wrap: wrap;
}

/* Outlined rather than filled: adding a task by hand is the fallback path, not
 * the product's point. It has to be findable, not loud. */
.new {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
  font: inherit;
  font-size: var(--text-sm);
  padding: var(--sp-2) var(--sp-3);
  color: var(--ink);
  background: var(--paper-raised);
  border: 1.5px solid var(--rule-strong);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: border-color var(--duration) var(--ease), color var(--duration) var(--ease);
}
.new:hover { color: var(--accent); border-color: var(--accent); }
/* Settings is consulted once and then left alone, so it sits a step back from
 * 新建 without hiding in a menu. */
.new.quiet { color: var(--ink-faint); border-color: var(--rule); border-width: 1px; }
.new.quiet:hover { color: var(--accent); border-color: var(--accent); }
/* Nothing connected: the accent outline is enough to pull the eye without a
 * badge or a banner, and it disappears the moment QQ attaches. */
.new.nudge { color: var(--accent); border-color: var(--accent); border-width: 1.5px; }

.live {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--text-xs);
  color: var(--ink-faint);
}
.pulse {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--none);
}
.live.on { color: var(--later); }
.live.stalled { color: var(--urgent); }
.live.stalled .pulse { background: var(--urgent); }
.live.on .pulse {
  background: var(--later);
  animation: breathe 2.4s var(--ease) infinite;
}
@keyframes breathe {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(74, 124, 89, 0.4); }
  50% { opacity: 0.75; box-shadow: 0 0 0 5px rgba(74, 124, 89, 0); }
}

.metrics {
  display: flex;
  align-items: baseline;
  gap: var(--sp-6);
  flex-wrap: wrap;
  padding: var(--sp-4) 0 var(--sp-5);
}
.metric { display: flex; flex-direction: column; gap: 2px; }
.metric .n {
  font-family: var(--font-numeric);
  font-size: var(--text-3xl);
  font-weight: 650;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.metric .l { font-size: var(--text-xs); color: var(--ink-faint); }
.metric.warn .n { color: var(--urgent); }
.metric.quiet .n { font-size: var(--text-xl); color: var(--ink-muted); }
.metric.spacer { flex: 1 1 auto; }

.error {
  margin: 0 0 var(--sp-4);
  padding: var(--sp-3) var(--sp-4);
  font-size: var(--text-sm);
  color: var(--accent-strong);
  background: var(--accent-wash);
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
}

.confirm {
  margin-bottom: var(--sp-6);
  padding: var(--sp-4);
  background: var(--soon-wash);
  border: 1px solid var(--soon);
  border-radius: var(--radius-lg);
}
.confirm h2 {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
  flex-wrap: wrap;
  margin: 0 0 var(--sp-3);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--soon);
}
.hint { font-size: var(--text-xs); font-weight: 400; color: var(--ink-muted); }

.group { margin-bottom: var(--sp-6); }
.group h2 {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin: 0 0 var(--sp-3);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--ink-muted);
}
.count {
  font-family: var(--font-numeric);
  font-size: var(--text-xs);
  padding: 1px var(--sp-2);
  color: var(--ink-faint);
  background: var(--paper-sunken);
  border-radius: 999px;
}

.grid {
  display: grid;
  gap: var(--sp-3);
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
}

/* The three seconds the demo video is built around. Deliberately not a bounce
 * or a slide-in: a brief warm wash plus a lift reads as "this is new" without
 * looking like a notification toast. */
.arrived {
  animation: arrive 3.2s var(--ease);
}
@keyframes arrive {
  0% {
    transform: translateY(-6px) scale(0.995);
    box-shadow: 0 0 0 3px var(--accent-wash), var(--shadow);
    background: var(--accent-wash);
  }
  18% {
    transform: none;
    box-shadow: 0 0 0 3px var(--accent-wash), var(--shadow);
  }
  100% {
    box-shadow: 0 0 0 0 transparent, var(--shadow-sm);
    background: var(--paper-raised);
  }
}

.state { padding: var(--sp-7) var(--sp-4); text-align: center; color: var(--ink-faint); }
.empty { max-width: 460px; margin: 0 auto; }
.empty-title { margin: 0 0 var(--sp-2); font-size: var(--text-lg); color: var(--ink-muted); }
.empty-body { margin: 0 0 var(--sp-4); font-size: var(--text-sm); line-height: var(--leading-normal); }
.empty-actions { margin: 0 0 var(--sp-4); }
.empty-hint { margin: 0; font-size: var(--text-xs); }
.empty-hint code {
  font-family: var(--font-numeric);
  padding: 2px var(--sp-2);
  background: var(--paper-sunken);
  border-radius: var(--radius-sm);
}

.boardfoot {
  padding-top: var(--sp-4);
  border-top: 1px solid var(--rule);
  font-size: var(--text-sm);
  color: var(--ink-faint);
}
.boardfoot label { display: inline-flex; align-items: center; gap: var(--sp-2); cursor: pointer; }

@media (max-width: 600px) {
  .app { padding: var(--sp-4) var(--sp-3) var(--sp-6); }
  .metrics { gap: var(--sp-5); }
  .metric .n { font-size: var(--text-2xl); }
  .grid { grid-template-columns: 1fr; }
}
</style>
