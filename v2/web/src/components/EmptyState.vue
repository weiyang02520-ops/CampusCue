<script setup lang="ts">
import { Inbox } from 'lucide-vue-next'
defineProps({ title: { type: String, required: true }, description: { type: String, required: true }, variant: { type: String, default: 'default' } })
</script>
<template><div class="empty-state" :class="`empty-${variant}`"><span class="empty-cue" aria-hidden="true"><i></i><b></b></span><span class="empty-icon"><Inbox :size="22" /></span><h3>{{ title }}</h3><p>{{ description }}</p><slot /></div></template>
