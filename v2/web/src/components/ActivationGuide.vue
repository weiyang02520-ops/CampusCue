<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpRight, CheckCircle2, Circle, MessageSquareText, Radio, Sparkles } from 'lucide-vue-next'
import type { Message, Source, Task } from '../types/api'
import { useResourcesStore } from '../stores/resources'

const props = defineProps<{ sources: Source[]; messages: Message[]; tasks: Task[] }>()
const resources = useResourcesStore()
const activeSource = computed(() => props.sources.find(source => source.enabled) || null)
const hasAgentConversation = computed(() => Boolean(activeSource.value && resources.threads.some(thread => thread.source_id === activeSource.value?.id && thread.message_count > 0)))
const reminderSummary = computed(() => {
  const failed = resources.reminders.find(reminder => reminder.error)
  if (failed) return '提醒发送失败：检查 QQ 连接后，后续提醒仍会按计划执行。'
  if (resources.reminders.some(reminder => reminder.status === 'fired')) return '最近提醒已触发（不等同于 QQ 已送达）。'
  if (resources.reminders.some(reminder => reminder.status === 'scheduled')) return '提醒已计划，届时会按来源发送。'
  return ''
})
const steps = computed(() => [
  { label: '连接一个消息来源', done: props.sources.length > 0 && Boolean(activeSource.value), icon: Radio, to: '/connections', action: '连接消息源' },
  { label: '收到并处理一条消息', done: props.messages.length > 0, icon: MessageSquareText, to: '/messages', action: '看处理记录' },
  { label: '生成一个可追溯任务', done: props.tasks.length > 0, icon: CheckCircle2, to: '/tasks', action: '看任务' },
  { label: '主动问 AI 一个问题', done: hasAgentConversation.value, icon: Sparkles, to: '/agent', action: hasAgentConversation.value ? '查看对话' : '开始对话' },
])
</script>

<template>
  <section class="activation-guide panel" aria-labelledby="activation-title">
    <div class="activation-heading">
      <div>
        <p class="section-kicker">第一次使用</p>
        <h2 id="activation-title">5 分钟启动</h2>
        <p>从来源到任务，再让 AI 基于真实任务回答一个问题。</p>
      </div>
      <span class="activation-count">{{ steps.filter(step => step.done).length }}/4</span>
    </div>
    <ol class="activation-steps">
      <li v-for="step in steps" :key="step.label" :class="{ done: step.done }">
        <component :is="step.done ? CheckCircle2 : Circle" :size="17" aria-hidden="true" />
        <span>{{ step.label }}</span>
        <RouterLink :to="step.to" class="activation-action">{{ step.action }} <ArrowUpRight :size="13" /></RouterLink>
      </li>
    </ol>
    <p v-if="!activeSource" class="activation-note">先连接一个消息来源，CampusCue 才能开始提取校园事务。</p>
    <p v-else-if="!props.messages.length" class="activation-note">来源已准备好；收到一条消息后，这里会出现处理结果。</p>
    <p v-if="reminderSummary" class="activation-note activation-reminder-status" role="status">{{ reminderSummary }}</p>
  </section>
</template>
