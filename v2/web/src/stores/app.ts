import { defineStore } from 'pinia'
import { ref } from 'vue'
export const useAppStore = defineStore('app', () => {
  const theme = ref<'light' | 'dark'>((localStorage.getItem('campuscue-theme') as 'light' | 'dark') || 'light')
  const online = ref(true); const notice = ref(''); let timer: number | undefined
  function setTheme(value: 'light' | 'dark') { theme.value = value; localStorage.setItem('campuscue-theme', value); document.documentElement.dataset.theme = value }
  function toast(message: string) { notice.value = message; window.clearTimeout(timer); timer = window.setTimeout(() => notice.value = '', 3600) }
  return { theme, online, notice, setTheme, toast }
})
