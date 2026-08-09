<script setup>
/**
 * The alarms that are actually scheduled.
 *
 * This exists because "it will remind you" is the product's central claim and
 * the least verifiable thing on the board. A card showing 还剩 3 天 proves a row
 * in a table; it says nothing about whether anything will fire. This reads the
 * cron table itself, so an empty list is a real answer -- the scheduler is not
 * bound -- rather than a computed list of what *should* exist.
 *
 * Collapsed by default. It is evidence, consulted once, not something to scan
 * every time the board is opened.
 */
import { computed, ref } from 'vue'

const props = defineProps({
  reminders: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh'])

const open = ref(false)

function toggle() {
  open.value = !open.value
  if (open.value) emit('refresh')
}

const pad = (n) => String(n).padStart(2, '0')

function clock(iso) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Grouped by day so a task with three reminders reads as one plan rather than
 *  three unrelated rows. */
const days = computed(() => {
  const buckets = new Map()
  for (const r of props.reminders) {
    if (!r.fire_at) continue
    const d = new Date(r.fire_at)
    const key = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    if (!buckets.has(key)) {
      const week = '日一二三四五六'[d.getDay()]
      buckets.set(key, {
        key,
        label: `${d.getMonth() + 1}月${d.getDate()}日 周${week}`,
        items: [],
      })
    }
    buckets.get(key).items.push(r)
  }
  return [...buckets.values()]
})

const next = computed(() => {
  const upcoming = props.reminders.filter((r) => r.fire_at)
  return upcoming.length ? upcoming[0] : null
})
</script>

<template>
  <section class="reminders">
    <button class="bar" type="button" :aria-expanded="open" @click="toggle">
      <span class="chev" :class="{ open }" aria-hidden="true">›</span>
      <span class="bar-title">已排提醒</span>
      <span class="n">{{ reminders.length }}</span>
      <!-- The next firing time is shown on the collapsed bar: it is the one fact
           worth having without opening anything. -->
      <span v-if="next" class="peek">
        下一条 {{ clock(next.fire_at) }} · {{ next.task_title }}
      </span>
      <span v-else-if="!loading" class="peek quiet">暂无</span>
    </button>

    <div v-if="open" class="body">
      <p v-if="loading" class="state">读取中…</p>

      <p v-else-if="!reminders.length" class="state">
        当前没有已排的提醒。任务有截止时间、且调度器已启动时，提醒会自动出现在这里。
      </p>

      <div v-else class="days">
        <section v-for="day in days" :key="day.key" class="day">
          <h3>{{ day.label }}</h3>
          <ul>
            <li v-for="r in day.items" :key="r.job_id">
              <span class="time">{{ pad(new Date(r.fire_at).getHours()) }}:{{ pad(new Date(r.fire_at).getMinutes()) }}</span>
              <span class="title">{{ r.task_title }}</span>
              <span v-if="r.label" class="label">{{ r.label }}</span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </section>
</template>

<style scoped>
.reminders {
  margin-bottom: var(--sp-5);
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
}

.bar {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  width: 100%;
  font: inherit;
  font-size: var(--text-sm);
  padding: var(--sp-3) var(--sp-4);
  color: var(--ink-muted);
  background: none;
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
  text-align: left;
}
.bar:hover { background: var(--paper-sunken); }
.bar-title { font-weight: 600; color: var(--ink); }

.chev {
  color: var(--ink-faint);
  transition: transform var(--duration) var(--ease);
}
.chev.open { transform: rotate(90deg); }

.n {
  font-family: var(--font-numeric);
  font-size: var(--text-xs);
  padding: 1px var(--sp-2);
  color: var(--ink-faint);
  background: var(--paper-sunken);
  border-radius: 999px;
}

.peek {
  margin-left: auto;
  font-family: var(--font-numeric);
  font-size: var(--text-xs);
  color: var(--ink-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.peek.quiet { font-family: var(--font-sans); }

.body { padding: 0 var(--sp-4) var(--sp-4); }
.state {
  margin: 0;
  padding: var(--sp-2) 0;
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
  color: var(--ink-faint);
}

.days { display: flex; flex-direction: column; gap: var(--sp-4); }
.day h3 {
  margin: 0 0 var(--sp-2);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--ink-faint);
  padding-bottom: var(--sp-1);
  border-bottom: 1px solid var(--rule);
}
.day ul { margin: 0; padding: 0; list-style: none; }
.day li {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
  padding: var(--sp-1) 0;
  font-size: var(--text-sm);
}

.time {
  flex: 0 0 auto;
  font-family: var(--font-numeric);
  font-variant-numeric: tabular-nums;
  color: var(--accent);
  font-weight: 600;
}
.title {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.label {
  flex: 0 0 auto;
  font-size: var(--text-xs);
  padding: 1px var(--sp-2);
  color: var(--ink-faint);
  background: var(--paper-sunken);
  border-radius: var(--radius-sm);
}
</style>
