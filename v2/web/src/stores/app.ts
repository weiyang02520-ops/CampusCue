import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
export type ThemePreference = 'system' | 'light' | 'dark'
export type VisualStyle = 'glass' | 'dark' | 'neumorphism'
type ResolvedTheme = 'light' | 'dark'
export const useAppStore = defineStore('app', () => {
  const savedTheme = localStorage.getItem('campuscue-theme') as ThemePreference | null
  const theme = ref<ThemePreference>(savedTheme === 'system' || savedTheme === 'dark' || savedTheme === 'light' ? savedTheme : 'light')
  const savedVisualStyle = localStorage.getItem('campuscue-visual-style') as VisualStyle | null
  const visualStyle = ref<VisualStyle>(savedVisualStyle === 'glass' || savedVisualStyle === 'dark' || savedVisualStyle === 'neumorphism' ? savedVisualStyle : 'glass')
  const systemTheme = ref<ResolvedTheme>(window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  const resolvedTheme = computed<ResolvedTheme>(() => theme.value === 'system' ? systemTheme.value : theme.value)
  const surfaceTheme = computed<ResolvedTheme>(() => visualStyle.value === 'dark' ? 'dark' : resolvedTheme.value)
  const online = ref(true); const notice = ref(''); let timer: number | undefined
  function applyTheme() { document.documentElement.dataset.theme = surfaceTheme.value; document.documentElement.dataset.visualTheme = visualStyle.value }
  function setTheme(value: ThemePreference) { theme.value = value; localStorage.setItem('campuscue-theme', value); applyTheme() }
  function setVisualStyle(value: VisualStyle) { visualStyle.value = value; localStorage.setItem('campuscue-visual-style', value); applyTheme() }
  function startSystemThemeSync() {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!media) return () => undefined
    const update = (event?: MediaQueryListEvent) => { systemTheme.value = event ? (event.matches ? 'dark' : 'light') : (media.matches ? 'dark' : 'light'); applyTheme() }
    update()
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }
  function toast(message: string) { notice.value = message; window.clearTimeout(timer); timer = window.setTimeout(() => notice.value = '', 3600) }
  return { theme, visualStyle, resolvedTheme, surfaceTheme, online, notice, setTheme, setVisualStyle, startSystemThemeSync, toast }
})
