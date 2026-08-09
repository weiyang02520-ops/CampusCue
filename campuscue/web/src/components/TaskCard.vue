<script setup>
/**
 * One task, as a card.
 *
 * The urgency encoding is the part that took the most thought. It has to be
 * legible from five metres away on a projector, which rules out relying on
 * colour: beamers shift hues and the back row cannot resolve a small tint.
 * So urgency is carried three ways at once, redundantly —
 *
 *   1. a left edge whose weight grows with urgency (3px → 6px)
 *   2. a countdown in large tabular figures, the biggest text on the card
 *   3. a word: 已逾期 / 今天 / 明天 / N天后
 *
 * Any one of the three survives a bad projector, colour-blindness, or a
 * greyscale printout of a slide.
 */
import { computed } from 'vue'

const props = defineProps({
  task: { type: Object, required: true },
  now: { type: Number, default: () => Date.now() },
})

defineEmits(['complete', 'dismiss', 'confirm', 'reopen', 'trace', 'edit'])

const TYPE_LABELS = {
  homework: '作业',
  exam: '考试',
  competition: '比赛',
  activity: '活动',
  notice: '通知',
}

const HOUR = 3600_000
const DAY = 24 * HOUR

const msLeft = computed(() => {
  if (!props.task.deadline) return null
  return new Date(props.task.deadline).getTime() - props.now
})

/** Urgency band. Thresholds are about how a student actually behaves: inside a
 *  day you drop what you are doing, inside three days you plan, beyond that you
 *  note it and move on. */
const urgency = computed(() => {
  const ms = msLeft.value
  if (ms === null) return 'none'
  if (ms < 0) return 'urgent'
  if (ms < DAY) return 'urgent'
  if (ms < 3 * DAY) return 'soon'
  return 'later'
})

/** The word form. Deliberately coarse — "3天后" is more useful than
 *  "2天17小时后", which invites arithmetic instead of action. Inside a day it
 *  becomes hourly, because that is when precision starts to matter. */
const countdown = computed(() => {
  const ms = msLeft.value
  if (ms === null) return { big: '待定', small: '无截止时间' }
  if (ms < 0) {
    const days = Math.floor(-ms / DAY)
    return {
      big: '已逾期',
      small: days >= 1 ? `逾期 ${days} 天` : `逾期 ${Math.floor(-ms / HOUR)} 小时`,
    }
  }
  if (ms < HOUR) return { big: `${Math.max(1, Math.round(ms / 60_000))} 分钟`, small: '马上截止' }
  if (ms < DAY) return { big: `${Math.floor(ms / HOUR)} 小时`, small: '今天截止' }
  const days = Math.floor(ms / DAY)
  if (days === 1) return { big: '明天', small: '还剩 1 天' }
  return { big: `${days} 天`, small: `还剩 ${days} 天` }
})

const deadlineText = computed(() => {
  if (!props.task.deadline) return null
  const d = new Date(props.task.deadline)
  const week = '日一二三四五六'[d.getDay()]
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}月${d.getDate()}日 周${week} ${pad(d.getHours())}:${pad(d.getMinutes())}`
})

const isPending = computed(() => props.task.status === 'pending_confirm')
const isDone = computed(() => props.task.status === 'done')
const isDismissed = computed(() => props.task.status === 'dismissed')
/** Finished either way: done or dismissed. Both are reversible, and the label
 *  says which one is being undone so 撤销 never reads as a guess. */
const isClosed = computed(() => isDone.value || isDismissed.value)
</script>

<template>
  <article
    class="card"
    :class="[`u-${urgency}`, { 'is-pending': isPending, 'is-done': isClosed }]"
  >
    <div class="edge" aria-hidden="true" />

    <div class="body">
      <header class="head">
        <span class="type" :class="`t-${task.task_type}`">
          {{ TYPE_LABELS[task.task_type] || task.task_type }}
        </span>
        <span v-if="isPending" class="badge badge-pending">待确认</span>
        <span v-if="task.source_kind === 'manual'" class="badge">手动</span>
        <!-- Two quiet links rather than icons or a kebab menu: the brief asks for
             clean at first glance with everything still findable, and a label a
             student can read beats a glyph they have to hover to identify. -->
        <div class="tools">
          <button class="link" type="button" @click="$emit('trace', task)">
            为什么？
          </button>
          <button v-if="!isClosed" class="link" type="button" @click="$emit('edit', task)">
            修改
          </button>
        </div>
      </header>

      <h3 class="title">{{ task.title }}</h3>

      <div class="when">
        <div class="count" :class="`u-${urgency}`">
          <span class="count-big">{{ countdown.big }}</span>
          <span class="count-small">{{ countdown.small }}</span>
        </div>
        <div v-if="deadlineText" class="abs">
          {{ deadlineText }}
          <span v-if="!task.deadline_is_explicit" class="inferred" title="原文未写明具体时间，由系统推断">
            推断
          </span>
        </div>
      </div>

      <dl v-if="task.location || task.items?.length" class="facts">
        <template v-if="task.location">
          <dt>地点</dt>
          <dd>{{ task.location }}</dd>
        </template>
        <template v-if="task.items?.length">
          <dt>携带</dt>
          <dd class="items">
            <span v-for="item in task.items" :key="item" class="item">{{ item }}</span>
          </dd>
        </template>
      </dl>

      <footer class="foot">
        <p class="src">
          <template v-if="task.source_group_name">
            来自 {{ task.source_group_name }}<template v-if="task.source_sender_name"> · {{ task.source_sender_name }}</template>
          </template>
          <template v-else>手动添加</template>
        </p>
        <!-- A closed card offers only 撤销. Both 完成 and 忽略 are one-click and
             land next to each other, so mis-clicking is a matter of when, not if;
             an undo is cheaper than a confirmation dialog on every click. -->
        <div class="actions">
          <button v-if="isClosed" class="btn" type="button" @click="$emit('reopen', task)">
            撤销{{ isDismissed ? '忽略' : '完成' }}
          </button>
          <template v-else>
            <button v-if="isPending" class="btn btn-primary" type="button" @click="$emit('confirm', task)">
              是任务
            </button>
            <button v-else class="btn" type="button" @click="$emit('complete', task)">
              完成
            </button>
            <button class="btn btn-quiet" type="button" @click="$emit('dismiss', task)">
              {{ isPending ? '不是' : '忽略' }}
            </button>
          </template>
        </div>
      </footer>
    </div>
  </article>
</template>

<style scoped>
.card {
  position: relative;
  display: flex;
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: box-shadow var(--duration) var(--ease),
    transform var(--duration) var(--ease);
}

.card:hover {
  box-shadow: var(--shadow);
  transform: translateY(-1px);
}

/* Signal 1 of 3: edge weight. Grows with urgency so the shape of the list is
 * readable before any text is. */
.edge {
  flex: 0 0 auto;
  width: 3px;
  background: var(--none);
}
.u-later .edge { width: 3px; background: var(--later); }
.u-soon .edge { width: 5px; background: var(--soon); }
.u-urgent .edge { width: 6px; background: var(--urgent); }

.body {
  flex: 1 1 auto;
  min-width: 0;
  padding: var(--sp-4);
}

.head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-3);
}

.type {
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.02em;
  padding: 2px var(--sp-2);
  border-radius: var(--radius-sm);
  color: var(--paper-raised);
  background: var(--type-notice);
}
.t-homework { background: var(--type-homework); }
.t-exam { background: var(--type-exam); }
.t-competition { background: var(--type-competition); }
.t-activity { background: var(--type-activity); }
.t-notice { background: var(--type-notice); }

.badge {
  font-size: var(--text-xs);
  padding: 2px var(--sp-2);
  border: 1px solid var(--rule-strong);
  border-radius: var(--radius-sm);
  color: var(--ink-muted);
}
.badge-pending {
  color: var(--soon);
  border-color: var(--soon);
  background: var(--soon-wash);
}

.tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex: 0 0 auto;
}

.link {
  font: inherit;
  font-size: var(--text-xs);
  color: var(--ink-faint);
  background: none;
  border: none;
  border-bottom: 1px dashed var(--rule-strong);
  padding: 0 0 1px;
  cursor: pointer;
  white-space: nowrap;
}
.link:hover { color: var(--accent); border-bottom-color: var(--accent); }

.title {
  margin: 0 0 var(--sp-3);
  font-size: var(--text-lg);
  font-weight: 600;
  line-height: var(--leading-tight);
  color: var(--ink);
  /* Chinese titles wrap badly on punctuation; keep them from breaking mid-word */
  word-break: keep-all;
  overflow-wrap: anywhere;
}

.when {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
  flex-wrap: wrap;
  margin-bottom: var(--sp-3);
}

/* Signal 2 of 3: the countdown is the largest thing on the card. From the back
 * of a room this is what reads. */
.count {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
}
.count-big {
  font-family: var(--font-numeric);
  font-size: var(--text-2xl);
  font-weight: 650;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}
/* Signal 3 of 3: the word. Survives greyscale and colour-blindness. */
.count-small {
  font-size: var(--text-sm);
  color: var(--ink-muted);
}
.u-urgent .count-big { color: var(--urgent); }
.u-soon .count-big { color: var(--soon); }
.u-later .count-big { color: var(--later); }
.u-none .count-big { color: var(--none); font-size: var(--text-xl); }

.abs {
  font-family: var(--font-numeric);
  font-size: var(--text-sm);
  color: var(--ink-muted);
  font-variant-numeric: tabular-nums;
}

.inferred {
  font-family: var(--font-sans);
  font-size: var(--text-xs);
  padding: 1px 5px;
  margin-left: var(--sp-1);
  color: var(--ink-faint);
  background: var(--paper-sunken);
  border-radius: var(--radius-sm);
  cursor: help;
}

.facts {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--sp-1) var(--sp-3);
  margin: 0 0 var(--sp-3);
  font-size: var(--text-sm);
}
.facts dt { color: var(--ink-faint); }
.facts dd { margin: 0; color: var(--ink); }

.items { display: flex; flex-wrap: wrap; gap: var(--sp-1); }
.item {
  padding: 1px var(--sp-2);
  background: var(--paper-sunken);
  border: 1px solid var(--rule);
  border-radius: var(--radius-sm);
}

.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding-top: var(--sp-3);
  border-top: 1px solid var(--rule);
}

.src {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--ink-faint);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.actions { display: flex; gap: var(--sp-2); flex: 0 0 auto; }

.btn {
  font: inherit;
  font-size: var(--text-sm);
  padding: var(--sp-1) var(--sp-3);
  color: var(--ink);
  background: var(--paper-raised);
  border: 1px solid var(--rule-strong);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--duration) var(--ease), border-color var(--duration) var(--ease);
}
.btn:hover { background: var(--paper-sunken); border-color: var(--ink-faint); }
.btn-primary {
  color: #fff;
  background: var(--accent);
  border-color: var(--accent);
}
.btn-primary:hover { background: var(--accent-strong); border-color: var(--accent-strong); }
.btn-quiet { color: var(--ink-faint); border-color: var(--rule); }

.is-done { opacity: 0.55; }
.is-done .title { text-decoration: line-through; text-decoration-thickness: 1.5px; }
.is-pending { background: linear-gradient(var(--soon-wash), var(--soon-wash)) padding-box; }

@media (max-width: 520px) {
  .foot { flex-direction: column; align-items: stretch; }
  .actions { justify-content: flex-end; }
}
</style>
