import { onMounted, onUnmounted } from 'vue'
import { useAppStore } from '../stores/app'
import { useTasksStore } from '../stores/tasks'
import { useResourcesStore } from '../stores/resources'
export function useSse() {
  const app = useAppStore(); const tasks = useTasksStore(); const resources = useResourcesStore(); let source: EventSource | null = null; let retry = 0; let timer: number | undefined
  const refresh = () => { void tasks.load(); void resources.loadAll() }
  function connect() { source?.close(); source = new EventSource('/api/v1/stream'); source.onopen = () => { app.online = true; retry = 0 }; source.onerror = () => { app.online = false; source?.close(); const delay = Math.min(30_000, 800 * 2 ** retry++); timer = window.setTimeout(connect, delay) }; source.onmessage = (event) => { try { const data = JSON.parse(event.data); if (data.type || data.event) refresh() } catch {} } }
  onMounted(connect); onUnmounted(() => { source?.close(); window.clearTimeout(timer) }); return { connect }
}
