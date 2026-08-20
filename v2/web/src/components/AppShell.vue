<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { Home, ListTodo, CalendarDays, Sparkles, MessageSquare, Cable, Cpu, Settings, Wifi, WifiOff, Moon, Sun, ChevronRight } from 'lucide-vue-next'
import { useAppStore } from '../stores/app'
import AppDialog from './AppDialog.vue'

const app = useAppStore()
const route = useRoute()
const items = [{ to:'/', label:'总览', icon:Home }, { to:'/tasks', label:'任务', icon:ListTodo }, { to:'/calendar', label:'日历', icon:CalendarDays }, { to:'/messages', label:'消息', icon:MessageSquare }, { to:'/agent', label:'AI 助手', icon:Sparkles }, { to:'/connections', label:'连接', icon:Cable }, { to:'/providers', label:'模型提供商', icon:Cpu }, { to:'/settings', label:'设置', icon:Settings }]
const moreItems = items.filter(item => ['/messages', '/connections', '/providers', '/settings'].includes(item.to))
const title = computed(() => items.find(i => i.to === route.path)?.label || '总览')
const moreOpen = ref(false)
const moreActive = computed(() => moreItems.some(item => item.to === route.path))
function closeMore() { moreOpen.value = false }
</script>
<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a><div class="app-shell">
    <aside class="sidebar" aria-label="主导航"><div class="brand"><span class="brand-mark">C</span><span>CampusCue</span></div><div class="workspace-label">我的校园工作台</div><nav><RouterLink v-for="item in items" :key="item.to" :to="item.to" :aria-current="route.path === item.to ? 'page' : undefined"><component :is="item.icon" :size="18" stroke-width="1.8" /><span>{{ item.label }}</span></RouterLink></nav><div class="sidebar-foot"><div class="system-pill"><span class="status-dot" :class="{ offline: !app.online }"></span><span>{{ app.online ? '本地服务正常' : '正在重连服务' }}</span></div><button class="nav-link theme-toggle" @click="app.setTheme(app.theme === 'light' ? 'dark' : 'light')"><component :is="app.theme === 'light' ? Moon : Sun" :size="17" /><span>{{ app.theme === 'light' ? '切换深色模式' : '切换浅色模式' }}</span></button></div></aside>
    <main id="main-content" class="main-column"><header class="topbar"><div><p class="eyebrow">{{ title }}</p><h1>{{ title }}</h1></div><div class="topbar-actions"><div class="connection-indicator" :class="{ offline: !app.online }"><component :is="app.online ? Wifi : WifiOff" :size="15" />{{ app.online ? '已连接' : '离线' }}</div></div></header><slot /></main>
    <nav class="mobile-nav" aria-label="移动端主导航"><RouterLink to="/" aria-label="总览"><Home :size="20" /><span>总览</span></RouterLink><RouterLink to="/tasks" aria-label="任务"><ListTodo :size="20" /><span>任务</span></RouterLink><RouterLink to="/calendar" aria-label="日历"><CalendarDays :size="20" /><span>日历</span></RouterLink><RouterLink to="/agent" aria-label="AI 助手"><Sparkles :size="20" /><span>AI</span></RouterLink><button class="mobile-more-trigger" :class="{ active: moreActive }" aria-label="更多" aria-haspopup="dialog" :aria-expanded="moreOpen" @click="moreOpen = true"><Settings :size="20" /><span>更多</span></button></nav>
    <AppDialog :open="moreOpen" title="更多" variant="sheet" @close="closeMore"><nav class="mobile-more-list" aria-label="更多页面"><RouterLink v-for="item in moreItems" :key="item.to" :to="item.to" :class="{ active: item.to === route.path }" @click="closeMore"><component :is="item.icon" :size="19" /><span>{{ item.label }}</span><ChevronRight :size="16" /></RouterLink></nav></AppDialog>
    <div v-if="app.notice" class="toast" role="status">{{ app.notice }}</div>
  </div>
</template>
