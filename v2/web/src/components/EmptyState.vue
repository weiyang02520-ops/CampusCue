<script setup lang="ts">
import { Inbox } from 'lucide-vue-next'
defineProps({ title: { type: String, required: true }, description: { type: String, required: true } })
</script>
<template><div class="empty-state"><Inbox :size="24" /><h3>{{ title }}</h3><p>{{ description }}</p><slot /></div></template>
