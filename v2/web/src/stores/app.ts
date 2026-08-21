import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
export type ThemePreference = 'system' | 'light' | 'dark'
type ResolvedTheme = 'light' | 'dark'
export const useAppStore = defineStore('app', () => {
  const savedTheme = localStorage.getItem('campuscue-theme') as ThemePreference | null
  const theme = ref<ThemePreference>(savedTheme === 'system' || savedTheme === 'dark' || savedTheme === 'light' ? savedTheme : 'light')
  const systemTheme = ref<ResolvedTheme>(window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  const resolvedTheme = computed<ResolvedTheme>(() => theme.value === 'system' ? systemTheme.value : theme.value)
  const online = ref(true); const notice = ref(''); let timer: number | undefined
  function applyTheme() { document.documentElement.dataset.theme = resolvedTheme.value }
  function setTheme(value: ThemePreference) { theme.value = value; localStorage.setItem('campuscue-theme', value); applyTheme() }
  function startSystemThemeSync() {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!media) return () => undefined
    const update = (event?: MediaQueryListEvent) => { systemTheme.value = event ? (event.matches ? 'dark' : 'light') : (media.matches ? 'dark' : 'light'); applyTheme() }
    update()
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }
  function toast(message: string) { notice.value = message; window.clearTimeout(timer); timer = window.setTimeout(() => notice.value = '', 3600) }
  return { theme, resolvedTheme, online, notice, setTheme, startSystemThemeSync, toast }
})
