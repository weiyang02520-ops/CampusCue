<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { MoreHorizontal, Pencil, Trash2, EyeOff } from 'lucide-vue-next'
import type { Task } from '../types/api'

defineProps<{ task: Task }>()
const emit = defineEmits<{ dismiss: []; edit: []; remove: [] }>()
const open = ref(false)
const root = ref<HTMLElement | null>(null)
function closeOnOutside(event: MouseEvent) { if (root.value && !root.value.contains(event.target as Node)) open.value = false }
function onKey(event: KeyboardEvent) { if (event.key === 'Escape') open.value = false }
onMounted(() => { document.addEventListener('click', closeOnOutside); document.addEventListener('keydown', onKey) })
onUnmounted(() => { document.removeEventListener('click', closeOnOutside); document.removeEventListener('keydown', onKey) })
</script>

<template>
  <div ref="root" class="task-menu">
    <button class="icon-button" :aria-label="`更多操作：${task.title}`" :aria-expanded="open" @click.stop="open = !open"><MoreHorizontal :size="18" /></button>
    <div v-if="open" class="task-menu-popover" role="menu">
      <button role="menuitem" @click="open = false; emit('edit')"><Pencil :size="15" />编辑</button>
      <button v-if="task.status !== 'done' && task.status !== 'dismissed'" role="menuitem" @click="open = false; emit('dismiss')"><EyeOff :size="15" />忽略</button>
      <button role="menuitem" class="danger-item" @click="open = false; emit('remove')"><Trash2 :size="15" />删除</button>
    </div>
  </div>
</template>
