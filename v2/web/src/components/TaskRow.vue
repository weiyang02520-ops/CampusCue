<script setup lang="ts">
import { Check, Circle, Clock3, MoreHorizontal } from 'lucide-vue-next'
import type { Task } from '../types/api'
import { formatDate, formatTime } from '../composables/useFormat'
defineProps<{ task: Task }>()
const emit = defineEmits(['complete', 'dismiss'])
</script>
<template><article class="task-row" :class="[`task-${task.status}`, { overdue: task.deadline && new Date(task.deadline) < new Date() && task.status === 'pending' }]" :data-testid="`task-${task.id}`"><button class="task-check" :aria-label="task.status === 'completed' ? '已完成' : `完成任务：${task.title}`" @click="emit('complete')"><Check v-if="task.status === 'completed'" :size="15" /><Circle v-else :size="17" /></button><div class="task-main"><h3>{{ task.title }}</h3><p><span v-if="task.course">{{ task.course }}</span><span v-if="task.course && task.deadline"> · </span>{{ task.category }}</p></div><div v-if="task.deadline" class="task-deadline"><Clock3 :size="14" /><span>{{ formatDate(task.deadline) }}</span><small>{{ formatTime(task.deadline) }}</small></div><button class="icon-button" :aria-label="`忽略任务：${task.title}`" @click="emit('dismiss')"><MoreHorizontal :size="18" /></button></article></template>
