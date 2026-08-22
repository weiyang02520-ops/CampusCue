<script setup lang="ts">
import { computed, onActivated } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowUpRight, CheckCircle2, Inbox, Sparkles, CalendarClock, RefreshCw } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import TaskRow from '../components/TaskRow.vue'
import EmptyState from '../components/EmptyState.vue'
import { useTasksStore } from '../stores/tasks'
import { useResourcesStore } from '../stores/resources'
import { useAppStore } from '../stores/app'
import ActivationGuide from '../components/ActivationGuide.vue'
import { relative } from '../composables/useFormat'

const tasks = useTasksStore()
const resources = useResourcesStore()
const app = useAppStore()
onActivated(() => { void resources.loadThreads() })
const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone
const timezone = computed(() => resources.settings.settings.timezone || browserTimezone)
function dateKey(value: Date | string) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: timezone.value, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(value))
  const get = (type: string) => parts.find(part => part.type === type)?.value || ''
  return `${get('year')}-${get('month')}-${get('day')}`
}
function dateLabel(value: Date) {
  const parts = new Intl.DateTimeFormat('zh-CN', { timeZone: timezone.value, weekday: 'long', month: 'numeric', day: 'numeric' }).formatToParts(value)
  const get = (type: string) => parts.find(part => part.type === type)?.value || ''
  return `${get('weekday')}，${get('month')} 月 ${get('day')} 日`
}
const now = computed(() => new Date())
const todayKey = computed(() => dateKey(now.value))
const weekDays = computed(() => Array.from({ length: 7 }, (_, offset) => { const date = new Date(now.value); date.setDate(date.getDate() + offset); const weekday = new Intl.DateTimeFormat('zh-CN', { timeZone: timezone.value, weekday: 'short' }).format(date).replace(/^周/, ''); return { key: dateKey(date), label: weekday, active: offset === 0 } }))
const weekKeys = computed(() => new Set(weekDays.value.map(day => day.key)))
const pending = computed(() => tasks.items.filter(task => task.status === 'pending' || task.status === 'pending_confirm'))
function sourceName(sourceId: number | null) { const source = resources.sources.find(item => item.id === sourceId); return source?.name || source?.conversation_id || null }
const today = computed(() => pending.value.filter(task => task.deadline && dateKey(task.deadline) === todayKey.value).slice(0, 3))
const weekPending = computed(() => pending.value.filter(task => task.deadline && weekKeys.value.has(dateKey(task.deadline))))
const upcoming = computed(() => pending.value.filter(task => !today.value.some(todayTask => todayTask.id === task.id)).sort((a, b) => { if (!a.deadline) return 1; if (!b.deadline) return -1; return a.deadline.localeCompare(b.deadline) }).slice(0, 3))
const homeDateLabel = computed(() => dateLabel(now.value))
async function complete(id: number) { try { await tasks.mutate(id, 'complete'); app.toast('任务已完成') } catch { app.toast('保存失败，已恢复原状态') } }
async function dismiss(id: number) { try { await tasks.mutate(id, 'dismiss'); app.toast('任务已忽略') } catch { app.toast('保存失败，已恢复原状态') } }
</script>
<template><section class="page-content home-page"><PageHeader :eyebrow="homeDateLabel" title="今天，先处理最重要的事" description="把校园消息变成清晰的下一步。"><RouterLink class="button button-primary" to="/tasks">查看全部任务 <ArrowUpRight :size="16" /></RouterLink></PageHeader><ActivationGuide :sources="resources.sources" :messages="resources.messages" :tasks="tasks.items" /><div class="home-grid"><section class="panel today-panel"><div class="panel-heading"><div><p class="section-kicker">今天</p><h2>{{ today.length ? `${today.length} 件待处理` : '今天还没有紧急任务' }}</h2></div><CheckCircle2 :size="22" class="quiet-icon" /></div><div v-if="today.length" class="task-list"><TaskRow v-for="task in today" :key="task.id" :task="task" :source-name="sourceName(task.source_id)" @complete="complete(task.id)" @dismiss="dismiss(task.id)" /></div><EmptyState v-else variant="task" title="节奏不错" description="把新任务添加到工作台，之后就能在这里看到。"><RouterLink class="text-link" to="/tasks">添加一个任务 <ArrowUpRight :size="14" /></RouterLink></EmptyState></section><aside class="panel focus-panel"><div class="panel-heading"><div><p class="section-kicker">本周焦点</p><h2>把截止日期留在视线里</h2></div><CalendarClock :size="22" class="quiet-icon" /></div><div class="week-line"><span v-for="day in weekDays" :key="day.key" :class="{ 'week-active': day.active }">{{ day.label }}</span></div><div class="week-summary"><strong>{{ weekPending.length }}</strong><span>个本周进行中的任务</span></div><RouterLink class="subtle-link" to="/calendar">打开日历 <ArrowUpRight :size="14" /></RouterLink></aside></div><div class="section-divider"><span>接下来</span><RouterLink to="/tasks">全部任务 <ArrowUpRight :size="14" /></RouterLink></div><section class="panel upcoming-panel"><div v-if="upcoming.length" class="task-list"><TaskRow v-for="task in upcoming" :key="task.id" :task="task" :source-name="sourceName(task.source_id)" @complete="complete(task.id)" @dismiss="dismiss(task.id)" /></div><EmptyState v-else variant="task" title="队列是空的" description="还没有更多待办任务。" /></section><div class="home-lower"><section class="panel compact-panel"><div class="panel-heading"><div><p class="section-kicker">最近消息</p><h2>消息处理记录</h2></div><Inbox :size="20" class="quiet-icon" /></div><div v-if="resources.messages.length" class="message-preview"><div v-for="message in resources.messages.slice(0, 3)" :key="message.id" class="message-line"><span class="message-status" :class="message.status"></span><span>{{ message.had_task ? '已提取任务' : '已查看消息' }}</span><time>{{ relative(message.created_at) }}</time></div></div><p v-else class="muted-copy">接入消息源后，处理记录会显示在这里。</p><RouterLink class="subtle-link" to="/messages">查看消息记录 <ArrowUpRight :size="14" /></RouterLink></section><section class="panel compact-panel"><div class="panel-heading"><div><p class="section-kicker">AI 助手</p><h2>需要帮忙梳理吗？</h2></div><Sparkles :size="20" class="quiet-icon" /></div><p class="muted-copy">向助手描述一个校园事务，它会根据已连接的消息源给出下一步。</p><RouterLink class="button button-secondary full-button" to="/agent">开始对话 <ArrowUpRight :size="16" /></RouterLink></section></div><div class="system-strip"><RefreshCw :size="15" /><span>{{ app.online ? '本地服务已连接，数据会自动同步。' : '本地服务暂时不可用，正在重试。' }}</span><RouterLink to="/settings">查看状态</RouterLink></div></section></template>
