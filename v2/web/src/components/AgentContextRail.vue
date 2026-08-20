<script setup lang="ts">
import { computed } from 'vue'
import { CalendarClock, CheckCircle2, MessageCircle, ListTodo } from 'lucide-vue-next'
import type { Task, Source } from '../types/api'
import { formatDate } from '../composables/useFormat'

const props = defineProps<{ tasks: Task[]; source: Source | null }>()
const todayTasks = computed(() => { const now = new Date(); return props.tasks.filter(task => task.deadline && task.status !== 'done' && task.status !== 'dismissed' && new Date(task.deadline).toDateString() === now.toDateString()) })
</script>

<template>
  <aside class="agent-context panel" aria-label="当前上下文">
    <div class="context-rail-heading"><div><p class="section-kicker">当前上下文</p><h3>保持在同一条线上</h3></div><MessageCircle :size="18" /></div>
    <div class="context-rail-list">
      <div><span><MessageCircle :size="15" />当前来源</span><strong>{{ source?.name || source?.conversation_id || '未连接' }}</strong></div>
      <div><span><CheckCircle2 :size="15" />今天待办</span><strong>{{ todayTasks.length }} 项</strong></div>
      <div><span><CalendarClock :size="15" />最近截止</span><strong>{{ tasks.find(task => task.deadline && task.status !== 'done' && task.status !== 'dismissed') ? formatDate(tasks.find(task => task.deadline && task.status !== 'done' && task.status !== 'dismissed')!.deadline) : '暂无' }}</strong></div>
      <div><span><ListTodo :size="15" />本周待处理</span><strong>{{ tasks.filter(task => task.deadline && task.status !== 'done' && task.status !== 'dismissed' && new Date(task.deadline).getTime() <= Date.now() + 7 * 86400000).length }} 项</strong></div>
    </div>
    <p class="muted-copy">上下文只用于这次对话，不会改变你的任务。</p>
  </aside>
</template>
