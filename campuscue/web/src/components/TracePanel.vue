<script setup>
/**
 * "Why did the AI decide this?"
 *
 * This panel is the product's answer to the only question that really matters
 * about an extraction system, and it has about five seconds to land. So it is
 * built as a vertical chain the eye can walk without reading closely:
 *
 *     原始消息  ← what a human actually wrote
 *        ↓
 *     L1 规则   ← free, no model involved
 *        ↓
 *     L2 模型   ← what the model claimed, plus its own words
 *        ↓
 *     L3 程序   ← the date, computed in code, not by the model
 *
 * The last step is the point. Every other extraction demo lets the model output
 * a date; showing that the arithmetic happened in code, from the message's own
 * timestamp, is what makes the deadline trustworthy rather than plausible.
 */
import { computed, nextTick, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps({
  detail: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

// Escape closes the panel even when focus never entered it (no inputs inside,
// so a keydown on the scrim itself would never fire -- the event goes to the
// body). Window-level listener with a guard is the reliable form.
function onKeydown(e) {
  if (e.key === 'Escape' && (props.detail || props.loading)) emit('close')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

// Move focus into the panel when it opens, so keyboard and screen-reader users
// are not left on the card that launched it.
watch(
  () => [props.detail, props.loading],
  () => {
    if (props.detail || props.loading) {
      nextTick(() => {
        const panel = document.querySelector('.scrim .panel')
        if (panel) panel.focus()
      })
    }
  },
)

const TIER = {
  l1: { label: 'L1 规则预筛', note: '本地规则，0 token' },
  l2: { label: 'L2 模型抽取', note: '豆包 · 结构化 JSON' },
  l3: { label: 'L3 程序换算', note: '代码计算，非模型推算' },
}

const trace = computed(() => props.detail?.trace?.[0] ?? null)
const task = computed(() => props.detail?.task ?? null)

const sentAt = computed(() => {
  const raw = trace.value?.message_sent_at ?? task.value?.source_sent_at
  if (!raw) return null
  const d = new Date(raw)
  const week = '日一二三四五六'[d.getDay()]
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} 周${week} ${pad(d.getHours())}:${pad(d.getMinutes())}`
})

const cost = computed(() => {
  if (!trace.value) return null
  const { prompt_tokens: p, completion_tokens: c, latency_ms: ms } = trace.value
  const parts = []
  if (p != null && c != null) parts.push(`${p + c} token`)
  if (ms != null) parts.push(`${(ms / 1000).toFixed(1)}s`)
  return parts.join(' · ') || null
})
</script>

<template>
  <div v-if="detail || loading" class="scrim" @click.self="$emit('close')">
    <aside class="panel" role="dialog" aria-label="抽取过程" tabindex="-1">
      <header class="head">
        <div>
          <h2>抽取过程</h2>
          <p v-if="task" class="sub">{{ task.title }}</p>
        </div>
        <button class="close" type="button" aria-label="关闭" @click="$emit('close')">
          ✕
        </button>
      </header>

      <div v-if="loading" class="loading">读取中…</div>

      <div v-else-if="trace" class="chain">
        <!-- Step 0: the actual message. Everything downstream is an
             interpretation of this, so it goes first and is quoted verbatim. -->
        <section class="step step-source">
          <div class="marker"><span class="dot" /></div>
          <div class="content">
            <h3>原始消息</h3>
            <p v-if="sentAt" class="meta">{{ sentAt }}</p>
            <blockquote class="raw">{{ trace.raw_text }}</blockquote>
            <p v-if="task?.source_group_name" class="meta">
              {{ task.source_group_name }}
              <template v-if="task.source_sender_name"> · {{ task.source_sender_name }}</template>
            </p>
          </div>
        </section>

        <section
          v-for="step in trace.steps"
          :key="step.tier"
          class="step"
          :class="`s-${step.tier}`"
        >
          <div class="marker"><span class="dot" /></div>
          <div class="content">
            <h3>
              {{ TIER[step.tier]?.label || step.tier }}
              <span class="note">{{ TIER[step.tier]?.note }}</span>
            </h3>
            <p class="summary">{{ step.summary }}</p>

            <!-- L1: which rules fired. Concrete evidence that the cheap filter
                 did real work rather than passing everything through. -->
            <ul v-if="step.tier === 'l1'" class="signals">
              <li v-for="sig in step.detail.signals || []" :key="sig">{{ sig }}</li>
            </ul>

            <!-- L2: the model's own justification, unedited. -->
            <p v-if="step.tier === 'l2' && step.detail.reason" class="reason">
              “{{ step.detail.reason }}”
            </p>

            <!-- L3: phrase in, instant out. The two sit side by side because the
                 gap between them is exactly what the code contributed. -->
            <div v-if="step.tier === 'l3' && step.detail.phrase" class="resolve">
              <code class="phrase">{{ step.detail.phrase }}</code>
              <span class="arrow" aria-hidden="true">→</span>
              <code class="instant">
                {{ step.detail.resolved
                  ? new Date(step.detail.resolved).toLocaleString('zh-CN', { hour12: false })
                  : '无法换算' }}
              </code>
              <span v-if="step.detail.basis" class="basis">规则 {{ step.detail.basis }}</span>
            </div>
          </div>
        </section>
      </div>

      <footer v-if="trace" class="foot">
        <span v-if="cost">{{ cost }}</span>
        <span v-if="trace.model" class="model">{{ trace.model }}</span>
        <details v-if="trace.raw_response" class="rawjson">
          <!-- Kept available on purpose: an auditor asking "is this JSON really
               from the model" can check. -->
          <summary>模型原始输出</summary>
          <pre>{{ trace.raw_response }}</pre>
        </details>
      </footer>
    </aside>
  </div>
</template>

<style scoped>
.scrim {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  justify-content: flex-end;
  background: rgba(31, 28, 23, 0.32);
  animation: fade var(--duration) var(--ease);
}

.panel {
  display: flex;
  flex-direction: column;
  width: min(520px, 100%);
  background: var(--paper);
  border-left: 1px solid var(--rule);
  box-shadow: var(--shadow-lg);
  animation: slide var(--duration) var(--ease);
}

@keyframes fade { from { opacity: 0 } }
@keyframes slide { from { transform: translateX(24px) } }

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-5) var(--sp-5) var(--sp-4);
  border-bottom: 1px solid var(--rule);
}
.head h2 { margin: 0; font-size: var(--text-lg); font-weight: 600; }
.sub {
  margin: var(--sp-1) 0 0;
  font-size: var(--text-sm);
  color: var(--ink-muted);
}

.close {
  flex: 0 0 auto;
  font: inherit;
  width: 28px; height: 28px;
  color: var(--ink-faint);
  background: none;
  border: 1px solid var(--rule);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.close:hover { color: var(--ink); background: var(--paper-sunken); }

.loading { padding: var(--sp-6); color: var(--ink-faint); }

.chain {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: var(--sp-5);
}

.step { display: flex; gap: var(--sp-4); }

/* The connecting line lives on the marker column, so the chain reads as one
 * continuous path rather than four separate boxes. */
.marker {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 12px;
}
.dot {
  width: 9px; height: 9px;
  margin-top: 6px;
  border-radius: 50%;
  background: var(--rule-strong);
}
.step:not(:last-child) .marker::after {
  content: '';
  flex: 1 1 auto;
  width: 1.5px;
  margin: var(--sp-2) 0;
  background: var(--rule);
}
.step-source .dot { background: var(--ink-faint); }
.s-l1 .dot { background: var(--later); }
.s-l2 .dot { background: var(--type-competition); }
.s-l3 .dot { background: var(--accent); }

.content { flex: 1 1 auto; min-width: 0; padding-bottom: var(--sp-5); }

.content h3 {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  flex-wrap: wrap;
  margin: 0 0 var(--sp-2);
  font-size: var(--text-base);
  font-weight: 600;
}
.note { font-size: var(--text-xs); font-weight: 400; color: var(--ink-faint); }
.meta { margin: 0 0 var(--sp-2); font-size: var(--text-xs); color: var(--ink-faint); }

.raw {
  margin: 0 0 var(--sp-2);
  padding: var(--sp-3);
  font-size: var(--text-base);
  line-height: var(--leading-normal);
  background: var(--paper-sunken);
  border-left: 3px solid var(--rule-strong);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

.summary { margin: 0 0 var(--sp-2); font-size: var(--text-sm); color: var(--ink-muted); }

.signals {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-1);
  margin: 0;
  padding: 0;
  list-style: none;
}
.signals li {
  font-family: var(--font-numeric);
  font-size: var(--text-xs);
  padding: 2px var(--sp-2);
  color: var(--ink-muted);
  background: var(--later-wash);
  border-radius: var(--radius-sm);
}

.reason {
  margin: 0;
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
  color: var(--ink);
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius-sm);
}

.resolve {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2);
  font-size: var(--text-sm);
}
.phrase, .instant {
  font-family: var(--font-numeric);
  padding: 3px var(--sp-2);
  border-radius: var(--radius-sm);
}
.phrase { background: var(--paper-sunken); color: var(--ink-muted); }
.instant { background: var(--accent-wash); color: var(--accent-strong); font-weight: 600; }
.arrow { color: var(--ink-faint); }
.basis { font-size: var(--text-xs); color: var(--ink-faint); }

.foot {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex-wrap: wrap;
  padding: var(--sp-3) var(--sp-5);
  font-family: var(--font-numeric);
  font-size: var(--text-xs);
  color: var(--ink-faint);
  border-top: 1px solid var(--rule);
  background: var(--paper-sunken);
}
.model { margin-right: auto; }

.rawjson summary { cursor: pointer; }
.rawjson pre {
  max-height: 160px;
  overflow: auto;
  margin: var(--sp-2) 0 0;
  padding: var(--sp-2);
  font-size: var(--text-xs);
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius-sm);
}

@media (max-width: 640px) {
  .panel { width: 100%; border-left: none; }
}
</style>
