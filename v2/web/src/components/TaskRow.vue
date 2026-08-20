<script setup lang="ts">
import { Check, Circle, Clock3, MoreHorizontal } from 'lucide-vue-next'
import type { Task } from '../types/api'
import { formatDate, formatTime } from '../composables/useFormat'
import { taskCategoryLabel, taskStatusLabel } from '../utils/taskLabels'
defineProps<{ task: Task }>()
const emit = defineEmits(['complete', 'dismiss'])
function deadlineTone(deadline?: string | null) { if (!deadline) return ''; const delta = new Date(deadline).getTime() - Date.now(); if (delta < 0) return 'deadline-overdue'; if (delta <= 86_400_000) return 'deadline-critical'; if (delta <= 604_800_000) return 'deadline-soon'; return '' }
</script>
<template><article class="task-row" :class="[`task-${task.status}`, { overdue: task.deadline && new Date(task.deadline) < new Date() && (task.status === 'pending' || task.status === 'pending_confirm') }]" :data-testid="`task-${task.id}`"><button class="task-check" :aria-label="task.status === 'done' ? '已完成' : `完成任务：${task.title}`" @click="emit('complete')"><Check v-if="task.status === 'done'" :size="15" /><Circle v-else :size="17" /></button><div class="task-main"><h3>{{ task.title }}</h3><p><span v-if="task.course" class="task-course">{{ task.course }}</span><span v-if="task.course && task.deadline"> · </span><span class="task-category" :class="task.category">{{ taskCategoryLabel(task.category) }}</span><span v-if="taskStatusLabel(task.status)" class="task-status-badge">{{ taskStatusLabel(task.status) }}</span></p></div><div v-if="task.deadline" class="task-deadline" :class="deadlineTone(task.deadline)"><Clock3 :size="14" /><span>{{ formatDate(task.deadline) }}</span><small>{{ formatTime(task.deadline) }}</small></div><button v-if="task.status !== 'done' && task.status !== 'dismissed'" class="icon-button" :aria-label="`忽略任务：${task.title}`" @click="emit('dismiss')"><MoreHorizontal :size="18" /></button></article></template>
