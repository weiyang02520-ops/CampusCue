import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
export type ThemePreference = 'system' | 'light' | 'dark'
export type VisualStylePreference = 'system' | 'glass' | 'dark' | 'neumorphism'
type ResolvedTheme = 'light' | 'dark'
export function backendThemeForVisualStyle(value: VisualStylePreference): ThemePreference { return value === 'system' ? 'system' : value === 'dark' ? 'dark' : 'light' }
export const useAppStore = defineStore('app', () => {
  const savedTheme = localStorage.getItem('campuscue-theme') as ThemePreference | null
  const theme = ref<ThemePreference>(savedTheme === 'system' || savedTheme === 'dark' || savedTheme === 'light' ? savedTheme : 'light')
  const savedVisualStyle = localStorage.getItem('campuscue-visual-style') as VisualStylePreference | null
  const hasStoredVisualStyle = Boolean(savedVisualStyle)
  const initialVisualStyle: VisualStylePreference = savedVisualStyle === 'system' || savedVisualStyle === 'glass' || savedVisualStyle === 'dark' || savedVisualStyle === 'neumorphism' ? savedVisualStyle : savedTheme === 'system' ? 'system' : savedTheme === 'dark' ? 'dark' : 'glass'
  const visualStyle = ref<VisualStylePreference>(initialVisualStyle)
  const systemTheme = ref<ResolvedTheme>(window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  const resolvedTheme = computed<ResolvedTheme>(() => theme.value === 'system' ? systemTheme.value : theme.value)
  const resolvedVisualStyle = computed<'glass' | 'dark' | 'neumorphism'>(() => visualStyle.value === 'system' ? (systemTheme.value === 'dark' ? 'dark' : 'glass') : visualStyle.value)
  const surfaceTheme = computed<ResolvedTheme>(() => resolvedVisualStyle.value === 'dark' ? 'dark' : 'light')
  const online = ref(true); const notice = ref(''); let timer: number | undefined
  function applyTheme() { document.documentElement.dataset.theme = surfaceTheme.value; document.documentElement.dataset.visualTheme = resolvedVisualStyle.value }
  function setTheme(value: ThemePreference) { theme.value = value; localStorage.setItem('campuscue-theme', value); applyTheme() }
  function setVisualStyle(value: VisualStylePreference) { visualStyle.value = value; theme.value = backendThemeForVisualStyle(value); localStorage.setItem('campuscue-visual-style', value); localStorage.setItem('campuscue-theme', theme.value); applyTheme() }
  function syncVisualStyleFromBackendTheme(value: ThemePreference) { if (hasStoredVisualStyle) { theme.value = backendThemeForVisualStyle(visualStyle.value); applyTheme(); return }; visualStyle.value = value === 'system' ? 'system' : value === 'dark' ? 'dark' : 'glass'; theme.value = value; applyTheme() }
  function startSystemThemeSync() {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!media) return () => undefined
    const update = (event?: MediaQueryListEvent) => { systemTheme.value = event ? (event.matches ? 'dark' : 'light') : (media.matches ? 'dark' : 'light'); applyTheme() }
    update()
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }
  function toast(message: string) { notice.value = message; window.clearTimeout(timer); timer = window.setTimeout(() => notice.value = '', 3600) }
  return { theme, visualStyle, resolvedVisualStyle, resolvedTheme, surfaceTheme, online, notice, setTheme, setVisualStyle, syncVisualStyleFromBackendTheme, startSystemThemeSync, toast }
})
