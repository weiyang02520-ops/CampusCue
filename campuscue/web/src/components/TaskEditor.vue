<script setup>
/**
 * Fixing what the extraction got wrong -- and typing in what it never saw.
 *
 * The trace panel answers "why did the AI decide this". This is the other half
 * of that answer: being able to correct it. A board that can only explain its
 * mistakes is a demo; one that can repair them is a tool.
 *
 * One dialog serves both editing and creating, keyed on whether the task it was
 * handed already has a `task_id`. Two nearly identical forms would drift apart,
 * and the fields are the same fields: a hand-typed task is a task, not a
 * different kind of object. What differs is the verb (PATCH a diff vs POST the
 * whole thing), and that is one branch in `payload`.
 *
 * Design constraint from the brief: clean at first glance, every feature still
 * findable. So the dialog opens showing only the two fields that are actually
 * wrong when an extraction is wrong -- the title and the deadline -- and the
 * rest (地点 / 携带 / 备注 / 类型) sits behind one disclosure. Nothing is
 * removed, but nothing competes with the deadline either. Creating is the one
 * case where the disclosure opens by default: a task nobody extracted has no
 * type either, and 类型 lives in there.
 *
 * The deadline input is `datetime-local`, which means it speaks the student's own
 * clock. Everything below converts at the boundary: local in the input, UTC ISO
 * on the wire. That is the same funnel the backend uses, for the same reason.
 */
import { computed, nextTick, ref, watch } from 'vue'

import { requestJson } from '../http.js'

const props = defineProps({
  /** An existing task to edit, or a blank one (no task_id) to create. */
  task: { type: Object, default: null },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['save', 'close', 'test-push'])

const TYPES = [
  { value: 'homework', label: '作业' },
  { value: 'exam', label: '考试' },
  { value: 'competition', label: '比赛' },
  { value: 'activity', label: '活动' },
  { value: 'notice', label: '通知' },
]

const title = ref('')
const taskType = ref('notice')
const deadline = ref('')
const location = ref('')
const itemsText = ref('')
const detail = ref('')
const more = ref(false)
const pushResult = ref(null)

/** UTC ISO → the `YYYY-MM-DDTHH:mm` a datetime-local input expects, in the
 *  browser's own timezone. Slicing the ISO string instead would render UTC and
 *  silently show the student a deadline eight hours off. */
function toInputValue(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  )
}

/** The input's local value → UTC ISO. `new Date('2026-08-14T23:59')` is parsed
 *  as local time by every current browser, so the offset is applied for us. */
function toIso(value) {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

/** Creating rather than editing. Drives the heading, the verb, and which
 *  controls make sense at all -- 立即试推 needs a task the server already has. */
const isNew = computed(() => Boolean(props.task) && !props.task.task_id)

watch(
  () => props.task,
  (task) => {
    pushResult.value = null
    more.value = false
    if (!task) return
    title.value = task.title || ''
    taskType.value = task.task_type || 'notice'
    deadline.value = toInputValue(task.deadline)
    location.value = task.location || ''
    itemsText.value = (task.items || []).join('、')
    detail.value = task.detail || ''
    // Open the disclosure when there is already something inside it, so an
    // existing location or item list is never hidden behind a click. Open it
    // when creating too: 类型 lives in there and a new task has none yet.
    more.value =
      !task.task_id ||
      Boolean(task.location || task.items?.length || task.detail)
    // Move focus into the dialog so keyboard and screen-reader users land on
    // the form instead of being left on the button that opened it.
    nextTick(() => {
      const sheet = document.querySelector('.scrim .sheet')
      if (sheet) sheet.focus()
    })
  },
  { immediate: true },
)

/** The items field, parsed. Both verbs need it. */
const parsedItems = computed(() =>
  itemsText.value
    .split(/[、,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean),
)

/** Only what the student actually changed. Sending the whole object would mark
 *  an untouched inferred deadline as explicitly confirmed, stripping the 推断
 *  badge off a time nobody verified. */
const changes = computed(() => {
  const task = props.task
  if (!task || isNew.value) return {}
  const next = {}
  const trimmed = title.value.trim()
  if (trimmed && trimmed !== task.title) next.title = trimmed
  if (taskType.value !== task.task_type) next.task_type = taskType.value

  const iso = toIso(deadline.value)
  const before = task.deadline ? new Date(task.deadline).toISOString() : null
  if (iso !== before) next.deadline = iso

  const loc = location.value.trim()
  if (loc !== (task.location || '')) next.location = loc || null

  if (parsedItems.value.join(' ') !== (task.items || []).join(' ')) {
    next.items = parsedItems.value
  }

  const note = detail.value.trim()
  if (note !== (task.detail || '')) next.detail = note || null
  return next
})

/** The whole object, for a task the server has never seen. */
const draft = computed(() => ({
  title: title.value.trim(),
  task_type: taskType.value,
  deadline: toIso(deadline.value),
  location: location.value.trim() || null,
  items: parsedItems.value,
  detail: detail.value.trim() || null,
}))

const titleEmpty = computed(() => !title.value.trim())
/** A new task needs only a title to be worth saving; an edit needs a diff. */
const dirty = computed(() =>
  isNew.value ? !titleEmpty.value : Object.keys(changes.value).length > 0,
)

function save() {
  if (!dirty.value || titleEmpty.value) return
  emit('save', {
    task: props.task,
    fields: isNew.value ? draft.value : changes.value,
    create: isNew.value,
  })
}

async function testPush() {
  pushResult.value = { pending: true }
  try {
    pushResult.value = await requestJson(
      `/api/v1/campus/tasks/${props.task.task_id}/remind-now`,
      { method: 'POST' },
    )
  } catch (err) {
    pushResult.value = { delivered: false, detail: err.message, preview: '' }
  }
}
</script>

<template>
  <div v-if="task" class="scrim" @click.self="$emit('close')">
    <!-- Escape closes: this opens over a board the student was reading, and a
         modal that traps them is worse than no modal. -->
    <div
      class="sheet"
      role="dialog"
      :aria-label="isNew ? '新建任务' : '编辑任务'"
      tabindex="-1"
      @keydown.esc="$emit('close')"
    >
      <header class="head">
        <h2>{{ isNew ? '新建任务' : '编辑任务' }}</h2>
        <button class="close" type="button" aria-label="关闭" @click="$emit('close')">
          ✕
        </button>
      </header>

      <form class="form" @submit.prevent="save">
        <label class="field">
          <span class="lbl">标题</span>
          <input
            v-model="title"
            class="input"
            type="text"
            :aria-invalid="titleEmpty"
            autocomplete="off"
          />
          <span v-if="titleEmpty" class="warn">标题不能为空</span>
        </label>

        <label class="field">
          <span class="lbl">
            截止时间
            <span v-if="task.deadline && !task.deadline_is_explicit" class="tag">
              当前时间由系统推断
            </span>
          </span>
          <input v-model="deadline" class="input" type="datetime-local" />
          <span v-if="isNew" class="hint">
            留空也可以，任务会进「待定时间」，之后再补也不影响。
          </span>
          <span v-else class="hint">
            改过之后就是你确认的时间，「推断」标记会去掉，提醒也会跟着重排。
          </span>
        </label>

        <!-- Everything below is real but rarely the thing that is wrong. One
             disclosure keeps the dialog to two fields on open. -->
        <button
          class="disclose"
          type="button"
          :aria-expanded="more"
          @click="more = !more"
        >
          {{ more ? '收起' : '更多字段' }}
          <span class="chev" :class="{ open: more }" aria-hidden="true">›</span>
        </button>

        <div v-if="more" class="extra">
          <label class="field">
            <span class="lbl">类型</span>
            <select v-model="taskType" class="input">
              <option v-for="t in TYPES" :key="t.value" :value="t.value">
                {{ t.label }}
              </option>
            </select>
          </label>

          <label class="field">
            <span class="lbl">地点</span>
            <input v-model="location" class="input" type="text" autocomplete="off" />
          </label>

          <label class="field">
            <span class="lbl">携带物品</span>
            <input v-model="itemsText" class="input" type="text" autocomplete="off" />
            <span class="hint">用顿号或逗号分隔，例如「学生证、计算器」</span>
          </label>

          <label class="field">
            <span class="lbl">备注</span>
            <textarea v-model="detail" class="input area" rows="3" />
          </label>
        </div>

        <!-- The reminder test lives here rather than on the card: it belongs
             next to the deadline it depends on, and it is the only way to prove
             the push path works without waiting for the real fire time. -->
        <section v-if="!isNew" class="push">
          <div class="push-row">
            <button class="btn" type="button" @click="testPush">
              立即试推一条提醒
            </button>
            <span class="hint">走真实推送通道，用来确认 QQ 那头收得到。</span>
          </div>
          <p v-if="pushResult?.pending" class="push-out">推送中…</p>
          <div v-else-if="pushResult" class="push-out">
            <p class="push-state" :class="{ ok: pushResult.delivered }">
              {{ pushResult.delivered ? '已送达' : '未送达' }}
              <span v-if="pushResult.detail" class="push-why">
                {{ pushResult.detail }}
              </span>
            </p>
            <pre v-if="pushResult.preview" class="preview">{{ pushResult.preview }}</pre>
          </div>
        </section>

        <footer class="foot">
          <span v-if="isNew" class="dirty quiet">手动添加，不经过 AI 判断</span>
          <span v-else-if="dirty" class="dirty">
            {{ Object.keys(changes).length }} 处改动
          </span>
          <span v-else class="dirty quiet">没有改动</span>
          <button class="btn btn-quiet" type="button" @click="$emit('close')">
            取消
          </button>
          <button
            class="btn btn-primary"
            type="submit"
            :disabled="!dirty || titleEmpty || saving"
          >
            {{ saving ? '保存中…' : isNew ? '添加' : '保存' }}
          </button>
        </footer>
      </form>
    </div>
  </div>
</template>

<style scoped>
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
  width: min(520px, 100%);
  max-height: min(88vh, 760px);
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
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4) var(--sp-5);
  border-bottom: 1px solid var(--rule);
}
.head h2 { margin: 0; font-size: var(--text-lg); font-weight: 600; }

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
  gap: var(--sp-4);
}

.field { display: flex; flex-direction: column; gap: var(--sp-2); }
.lbl {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  flex-wrap: wrap;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink-muted);
}
.tag {
  font-size: var(--text-xs);
  font-weight: 400;
  padding: 1px var(--sp-2);
  color: var(--soon);
  background: var(--soon-wash);
  border-radius: var(--radius-sm);
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
.input:focus {
  outline: none;
  border-color: var(--accent);
}
.input[aria-invalid='true'] { border-color: var(--urgent); }
.area { resize: vertical; line-height: var(--leading-normal); }
/* datetime-local renders its own numerals; keep them tabular so the field does
 * not shift width as digits change. */
input[type='datetime-local'] {
  font-family: var(--font-numeric);
  font-variant-numeric: tabular-nums;
}

.hint { font-size: var(--text-xs); color: var(--ink-faint); line-height: var(--leading-normal); }
.warn { font-size: var(--text-xs); color: var(--urgent); }

.disclose {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
  font: inherit;
  font-size: var(--text-sm);
  padding: 0;
  color: var(--ink-faint);
  background: none;
  border: none;
  cursor: pointer;
}
.disclose:hover { color: var(--accent); }
.chev {
  display: inline-block;
  transition: transform var(--duration) var(--ease);
}
.chev.open { transform: rotate(90deg); }

.extra {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  padding: var(--sp-4);
  background: var(--paper-sunken);
  border-radius: var(--radius);
}

.push {
  padding-top: var(--sp-4);
  border-top: 1px solid var(--rule);
}
.push-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex-wrap: wrap;
}
.push-out { margin: var(--sp-3) 0 0; font-size: var(--text-sm); }
.push-state { margin: 0; font-weight: 600; color: var(--urgent); }
.push-state.ok { color: var(--later); }
.push-why { font-weight: 400; color: var(--ink-faint); font-size: var(--text-xs); }
.preview {
  margin: var(--sp-2) 0 0;
  padding: var(--sp-3);
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
  white-space: pre-wrap;
  color: var(--ink);
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius-sm);
}

/* Sticky rather than simply last: with the disclosure open the form scrolls, and
 * a 保存 button below the fold reads as a dialog with no way to commit. Pinned to
 * the bottom of the scroll area it is always the thing under your thumb. */
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

@media (max-width: 520px) {
  .sheet { max-height: 94vh; }
  .foot { flex-wrap: wrap; }
  .dirty { width: 100%; margin-bottom: var(--sp-2); }
}
</style>
