<script setup>
/**
 * 接入与自检 -- getting 课讯 online without a terminal.
 *
 * The whole point is that a student's only manual step is a scan on their phone.
 * Everything else on this screen is a button: install NapCat, point it at our
 * port, start it, watch the QR appear, wait for the socket, pull the group list,
 * tick which groups to watch, prove a push arrives.
 *
 * Two things worth knowing about how it renders:
 *
 * - The QR is text. NapCat draws it with block characters on stdout, so a
 *   monospace box with tight line-height *is* a scannable code -- no image, no
 *   decoding. That is also why the panel must never let it wrap.
 * - Status is polled from one endpoint while the panel is open, so no two
 *   sections can disagree about whether QQ is connected.
 */
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'

import { requestJson } from '../http.js'

const props = defineProps({
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'changed'])

const API = '/api/v1/campus/setup'

const status = ref(null)
const log = ref({ log: '', qrcode: '', running: false })
const busy = ref('')
const note = ref('')
const noteOk = ref(true)
const showLog = ref(false)
let timer = null
let refreshing = false

async function call(path, options, timeoutMs = 15_000) {
  return requestJson(`${API}${path}`, options, { timeoutMs })
}

/** One poll = status + the NapCat log, so the QR and the connection badge always
 *  describe the same instant. */
async function refresh() {
  if (refreshing) return
  refreshing = true
  try {
    const [next, tail] = await Promise.all([
      call('/status'),
      call('/napcat/log?lines=200'),
    ])
    status.value = next
    log.value = tail
  } catch (err) {
    note.value = err.message
    noteOk.value = false
  } finally {
    refreshing = false
  }
}

/** 2s while open: fast enough that the QR appears to show up on its own after
 *  启动, slow enough to leave running on a projector. Stopped on close so a
 *  closed panel is not polling the backend for the rest of the session. */
watch(
  () => props.open,
  (open) => {
    if (open) {
      refresh()
      timer = setInterval(refresh, 2000)
    } else if (timer) {
      clearInterval(timer)
      timer = null
    }
    // Move focus into the dialog on open, for keyboard and screen-reader users.
    if (open) {
      nextTick(() => {
        const sheet = document.querySelector('.scrim .sheet')
        if (sheet) sheet.focus()
      })
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

/** Run one button's action, keeping its own spinner and reporting the result in
 *  place. Install downloads ~30MB from GitHub, which on a campus network has
 *  measured well under 1 MB/s, so `busy` is per-action rather than a single
 *  panel-wide flag -- otherwise every other button looks broken for a minute. */
async function act(key, path, options = { method: 'POST' }) {
  busy.value = key
  note.value = ''
  try {
    const timeoutMs = key === 'install' ? 300_000 : 60_000
    const result = await call(path, options, timeoutMs)
    if (Array.isArray(result)) {
      note.value = `已同步 ${result.length} 个群`
      noteOk.value = true
    } else {
      note.value = result.detail || '完成'
      noteOk.value = result.ok !== false
    }
    emit('changed')
  } catch (err) {
    note.value = err.message
    noteOk.value = false
  } finally {
    busy.value = ''
    refresh()
  }
}

async function toggleWatch(source) {
  const on = !source.enabled
  // Optimistic: the checkbox should move on click, and the 2s poll reconciles.
  source.enabled = on
  try {
    await call(`/groups/${encodeURIComponent(source.umo)}/watch?on=${on}`, {
      method: 'POST',
    })
    emit('changed')
  } catch (err) {
    source.enabled = !on
    note.value = err.message
    noteOk.value = false
  }
}

const napcat = computed(() => status.value?.napcat || {})
const link = computed(() => status.value?.link || {})
const sources = computed(() => status.value?.sources || [])
const watched = computed(() => sources.value.filter((s) => s.enabled).length)

/** Grouped for the report, in the order collect_checks emits them. */
const checkGroups = computed(() => {
  const out = []
  for (const check of status.value?.checks || []) {
    const last = out[out.length - 1]
    if (last && last.name === check.group) last.items.push(check)
    else out.push({ name: check.group, items: [check] })
  }
  return out
})

/** Which step the student is actually on.
 *
 * Shown as a single sentence at the top because the panel has five sections and
 * the useful question is never "what is the state of all of it" but "what do I
 * do next".
 */
const nextStep = computed(() => {
  const n = napcat.value
  if (link.value.connected) {
    return watched.value
      ? { text: '已接入，可以去看板了', done: true }
      : { text: '已连上 QQ。同步群列表，勾选要监听的群。' }
  }
  if (!n.supported) return { text: '非 Windows 环境，请手动安装并启动 NapCat' }
  if (!n.installed) return { text: '第一步：安装 NapCat（下载约 30MB）' }
  if (!n.running) return { text: '第二步：启动 NapCat，下面会出现登录二维码' }
  if (!log.value.qrcode) return { text: '正在等 NapCat 打印二维码…' }
  return { text: '第三步：用手机 QQ 扫下面的码' }
})
</script>

<template>
  <div v-if="open" class="scrim" @click.self="$emit('close')">
    <div
      class="sheet"
      role="dialog"
      aria-label="接入与自检"
      tabindex="-1"
      @keydown.esc="$emit('close')"
    >
      <header class="head">
        <div>
          <h2>接入与自检</h2>
          <p class="who">{{ nextStep.text }}</p>
        </div>
        <button class="close" type="button" aria-label="关闭" @click="$emit('close')">
          ✕
        </button>
      </header>

      <div class="body">
        <p v-if="note" class="note" :class="{ bad: !noteOk }" role="status">
          {{ note }}
        </p>

        <!-- Connection first: it is the one line that says whether any of this
             worked, and on a rehearsal it is the only line anyone reads. -->
        <section class="block">
          <div class="blockhead">
            <h3>QQ 连接</h3>
            <span class="badge" :class="{ on: link.connected }">
              {{ link.connected ? '已连接' : '未连接' }}
            </span>
          </div>
          <dl class="facts">
            <div><dt>登录账号</dt><dd>{{ link.accounts?.join(' / ') || '—' }}</dd></div>
            <div><dt>监听端口</dt><dd class="mono">{{ link.port || '—' }}</dd></div>
            <div><dt>NapCat 拨入地址</dt><dd class="mono">{{ napcat.ws_url || '—' }}</dd></div>
          </dl>
          <p v-if="link.detail" class="hint">{{ link.detail }}</p>
        </section>

        <section class="block">
          <div class="blockhead">
            <h3>NapCat</h3>
            <span class="badge" :class="{ on: napcat.running }">
              {{ napcat.detail || '—' }}
            </span>
          </div>

          <div class="actions">
            <button
              v-if="!napcat.installed"
              class="btn btn-primary"
              type="button"
              :disabled="busy === 'install' || napcat.installing || !napcat.supported"
              @click="act('install', '/napcat/install')"
            >
              {{ busy === 'install' || napcat.installing ? '下载安装中…' : '安装 NapCat' }}
            </button>
            <button
              v-else-if="!napcat.running"
              class="btn btn-primary"
              type="button"
              :disabled="busy === 'start'"
              @click="act('start', '/napcat/start')"
            >
              {{ busy === 'start' ? '启动中…' : '启动并出码' }}
            </button>
            <button
              v-else
              class="btn"
              type="button"
              :disabled="busy === 'stop' || !napcat.managed"
              :title="napcat.managed ? '' : '这个 NapCat 不是本程序启动的，不代为停止'"
              @click="act('stop', '/napcat/stop')"
            >
              停止
            </button>

            <button
              v-if="napcat.installed"
              class="btn btn-quiet"
              type="button"
              :disabled="busy === 'configure'"
              @click="act('configure', '/napcat/configure')"
            >
              重写连接配置
            </button>
            <span v-if="napcat.installed && !napcat.configured" class="warnpill">
              配置里的地址和当前端口不一致，点一下重写
            </span>
          </div>

          <p v-if="!napcat.installed && napcat.supported" class="hint">
            会从 NapCat 官方仓库下载 NapCat.Shell（约 30MB）到 <code>data/napcat</code>，
            并自动把反向 WebSocket 地址写好。前提是这台机器已经装了 QQ。
          </p>
        </section>

        <!-- The scan. Kept in its own section with nothing beside it: this is the
             one thing the student has to physically do. -->
        <section v-if="log.qrcode || (napcat.running && !link.connected)" class="block">
          <div class="blockhead">
            <h3>扫码登录</h3>
            <span class="hint">手机 QQ → 右上角 ＋ → 扫一扫</span>
          </div>
          <pre v-if="log.qrcode" class="qr">{{ log.qrcode }}</pre>
          <p v-else class="hint">NapCat 正在启动，二维码通常十几秒内出现…</p>
        </section>

        <section class="block">
          <div class="blockhead">
            <h3>监听哪些群</h3>
            <span class="hint">{{ watched }} / {{ sources.length }} 个群已监听</span>
          </div>
          <div class="actions">
            <button
              class="btn"
              type="button"
              :disabled="busy === 'sync' || !link.connected"
              :title="link.connected ? '' : '先扫码登录'"
              @click="act('sync', '/groups/sync')"
            >
              {{ busy === 'sync' ? '同步中…' : '同步 QQ 群列表' }}
            </button>
          </div>
          <ul v-if="sources.length" class="grouplist">
            <li v-for="source in sources" :key="source.umo">
              <label>
                <input
                  type="checkbox"
                  :checked="source.enabled"
                  @change="toggleWatch(source)"
                />
                <span class="gname">{{ source.label }}</span>
              </label>
              <span class="gstat">
                {{ source.messages_seen }} 条已读 · {{ source.open_tasks }} 个任务
              </span>
            </li>
          </ul>
          <p v-else class="hint">
            还没有群。扫码登录后点上面的同步，或者等群里有人说话。
          </p>
          <p class="hint">
            新同步进来的群默认不监听 —— 监听哪个群由你勾选，不由账号在哪些群里决定。
          </p>
        </section>

        <section class="block">
          <div class="blockhead">
            <h3>自检</h3>
            <span class="badge" :class="{ on: status && !status.problems }">
              {{ status ? (status.problems ? `${status.problems} 项待处理` : '全部就绪') : '读取中…' }}
            </span>
          </div>
          <div v-for="group in checkGroups" :key="group.name" class="checkgroup">
            <h4>{{ group.name }}</h4>
            <ul class="checks">
              <li v-for="item in group.items" :key="item.text" :class="{ bad: !item.ok }">
                <span class="mark" aria-hidden="true">{{ item.ok ? '✓' : '!' }}</span>
                {{ item.text }}
              </li>
            </ul>
          </div>
          <dl class="facts">
            <div>
              <dt>提醒调度</dt>
              <dd :class="{ bad: status && !status.scheduler_ready }">
                {{ status?.scheduler_ready ? '已就绪' : '未就绪' }}
              </dd>
            </div>
            <div>
              <dt>抽取模型</dt>
              <dd :class="{ bad: status && !status.extractor_ready }">
                {{ status?.extractor_ready ? '已配置' : '缺少 ARK_API_KEY' }}
              </dd>
            </div>
          </dl>
          <div class="actions">
            <button
              class="btn"
              type="button"
              :disabled="busy === 'selftest'"
              @click="act('selftest', '/selftest')"
            >
              {{ busy === 'selftest' ? '推送中…' : '给自己发一条测试消息' }}
            </button>
          </div>
          <p class="hint">
            走的是提醒用的同一条推送链路，收到就说明到时候的提醒也能到。
          </p>
        </section>

        <section class="block">
          <button class="disclose" type="button" @click="showLog = !showLog">
            {{ showLog ? '▾' : '▸' }} NapCat 日志
          </button>
          <pre v-if="showLog" class="logbox">{{ log.log || '（还没有日志）' }}</pre>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Same dialog chrome as SettingsPanel and TaskEditor. Three modals that looked
 * different would read as three different products. */
.scrim {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: grid;
  place-items: center;
  padding: var(--sp-4);
  background: rgba(31, 28, 23, 0.34);
  animation: fade var(--duration) var(--ease);
}
@keyframes fade { from { opacity: 0 } }

.sheet {
  width: min(640px, 100%);
  max-height: min(90vh, 880px);
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
/* The "what do I do next" line. Accent-coloured because on this screen it is the
 * only sentence that has to be read. */
.who { margin: 2px 0 0; font-size: var(--text-sm); color: var(--accent); }

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

.body {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: var(--sp-5);
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
}

.note {
  margin: 0;
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--text-sm);
  color: var(--later);
  background: var(--paper-sunken);
  border-left: 2px solid var(--later);
  border-radius: var(--radius-sm);
}
.note.bad { color: var(--accent-strong); background: var(--accent-wash); border-color: var(--accent); }

.block { display: flex; flex-direction: column; gap: var(--sp-3); }
.blockhead {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-3);
  flex-wrap: wrap;
  padding-bottom: var(--sp-2);
  border-bottom: 1px solid var(--rule);
}
.blockhead h3 { margin: 0; font-size: var(--text-sm); font-weight: 600; }

.badge {
  font-size: var(--text-xs);
  padding: 2px var(--sp-2);
  color: var(--ink-faint);
  background: var(--paper-sunken);
  border-radius: 999px;
}
.badge.on { color: #fff; background: var(--later); }

.facts { display: flex; flex-wrap: wrap; gap: var(--sp-2) var(--sp-5); margin: 0; }
.facts > div { display: flex; flex-direction: column; gap: 2px; }
.facts dt { font-size: var(--text-xs); color: var(--ink-faint); }
.facts dd { margin: 0; font-size: var(--text-sm); }
.facts dd.bad { color: var(--accent-strong); }
.mono { font-family: var(--font-numeric); font-variant-numeric: tabular-nums; }

.actions { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; }

.hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--ink-faint);
  line-height: var(--leading-normal);
}
.hint code {
  font-family: var(--font-numeric);
  padding: 1px var(--sp-1);
  background: var(--paper-sunken);
  border-radius: var(--radius-sm);
}
.warnpill {
  font-size: var(--text-xs);
  padding: 2px var(--sp-2);
  color: var(--accent-strong);
  background: var(--accent-wash);
  border-radius: var(--radius-sm);
}

/* The QR, and every declaration here is load-bearing on whether a phone reads it.
 *
 * NapCat draws the code with half-block characters, so one text line carries two
 * module rows: a module is one character advance wide and half a line tall. That
 * gives the geometry --
 *
 * - `line-height: 2ch` makes it square. 1ch is the advance width, so two module
 *   rows per line means the line must be twice that. A plain `line-height: 1`
 *   leaves modules 17% wider than tall, which decoders mostly tolerate and
 *   sometimes do not -- not a coin worth flipping while someone is on stage.
 * - The font stack is real monospace, not --font-numeric. That token leads with
 *   Inter, which has no block glyphs, so digits would come from Inter and blocks
 *   from a fallback -- and then `ch` measures the wrong font.
 * - `letter-spacing: 0` against any inherited tracking, `white-space: pre`
 *   against wrapping: a wrapped or gapped grid is not a QR code.
 * - `align-self: flex-start` keeps the white card the size of the code instead of
 *   stretching it across the panel, which read as a mostly-empty white slab with
 *   the code shoved into one corner.                                    */
.qr {
  margin: 0;
  align-self: flex-start;
  max-width: 100%;
  padding: var(--sp-3);
  overflow-x: auto;
  font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", ui-monospace, monospace;
  font-size: 10px;
  line-height: 2ch;
  letter-spacing: 0;
  white-space: pre;
  color: #000;
  background: #fff;
  border: 1px solid var(--rule);
  border-radius: var(--radius-sm);
}

.grouplist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.grouplist li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-2) 0;
  border-bottom: 1px solid var(--rule);
}
.grouplist label { display: flex; align-items: center; gap: var(--sp-2); cursor: pointer; }
.gname { font-size: var(--text-sm); }
.gstat {
  font-family: var(--font-numeric);
  font-size: var(--text-xs);
  color: var(--ink-faint);
  white-space: nowrap;
}

.checkgroup { display: flex; flex-direction: column; gap: var(--sp-1); }
.checkgroup h4 {
  margin: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--ink-faint);
}
.checks { list-style: none; margin: 0; padding: 0; }
.checks li {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
  color: var(--ink-muted);
}
.checks .mark { flex: 0 0 auto; color: var(--later); font-weight: 700; }
.checks li.bad { color: var(--accent-strong); }
.checks li.bad .mark { color: var(--accent); }

.disclose {
  font: inherit;
  font-size: var(--text-xs);
  align-self: flex-start;
  padding: 0;
  color: var(--ink-faint);
  background: none;
  border: none;
  cursor: pointer;
}
.disclose:hover { color: var(--accent); }

.logbox {
  margin: 0;
  max-height: 220px;
  overflow: auto;
  padding: var(--sp-3);
  font-family: var(--font-numeric);
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  color: var(--ink-muted);
  background: var(--paper-sunken);
  border: 1px solid var(--rule);
  border-radius: var(--radius-sm);
}

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

@media (max-width: 560px) {
  .sheet { max-height: 94vh; }
  .grouplist li { flex-direction: column; align-items: flex-start; gap: var(--sp-1); }
}
</style>
