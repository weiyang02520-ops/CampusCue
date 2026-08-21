<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { useAppStore } from './stores/app'
import { useTasksStore } from './stores/tasks'
import { useResourcesStore } from './stores/resources'
import { useSse } from './composables/useSse'
import AppShell from './components/AppShell.vue'
const app = useAppStore(); const tasks = useTasksStore(); const resources = useResourcesStore(); const route = useRoute(); useSse()
watch(() => app.resolvedTheme, value => document.documentElement.dataset.theme = value, { immediate: true })
let stopSystemThemeSync: () => void = () => undefined
onMounted(() => { stopSystemThemeSync = app.startSystemThemeSync(); void tasks.load(); void resources.loadAll() })
onUnmounted(() => stopSystemThemeSync())
</script>
<template><AppShell><RouterView v-slot="{ Component }"><KeepAlive><component :is="Component" :key="route.path" /></KeepAlive></RouterView></AppShell></template>
