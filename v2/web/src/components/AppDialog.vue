<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'
const props = defineProps<{ open: boolean; title: string; description?: string; variant?: 'dialog' | 'sheet' }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLElement>(); const previous = ref<HTMLElement | null>(null)
function keydown(event: KeyboardEvent) { if (event.key === 'Escape') emit('close') }
watch(() => props.open, async open => { if (open) { previous.value = document.activeElement as HTMLElement; await nextTick(); dialog.value?.focus(); document.addEventListener('keydown', keydown) } else { document.removeEventListener('keydown', keydown); previous.value?.focus() } })
onMounted(() => { if (props.open) document.addEventListener('keydown', keydown) }); onUnmounted(() => document.removeEventListener('keydown', keydown))
</script>
<template><Teleport to="body"><div v-if="open" class="dialog-backdrop" @click.self="emit('close')"><section ref="dialog" :class="['dialog', { 'dialog-sheet': variant === 'sheet' }]" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1"><header class="dialog-header"><div><h2>{{ title }}</h2><p v-if="description">{{ description }}</p></div><button class="icon-button" aria-label="关闭" @click="emit('close')"><X :size="18" /></button></header><div class="dialog-body"><slot /></div><footer v-if="$slots.footer" class="dialog-footer"><slot name="footer" /></footer></section></div></Teleport></template>
