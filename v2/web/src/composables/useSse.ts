import { onMounted, onUnmounted } from 'vue'
import { useAppStore } from '../stores/app'
import { useTasksStore } from '../stores/tasks'
import { useResourcesStore } from '../stores/resources'
export function useSse() {
  const app = useAppStore(); const tasks = useTasksStore(); const resources = useResourcesStore(); let controller: AbortController | null = null; let retry = 0; let timer: number | undefined
  const refresh = () => { void tasks.load(); void resources.loadAll() }
  const taskEvents = new Set(['task.created', 'task.updated', 'task.completed', 'task.dismissed', 'task.deleted'])
  const allEvents = new Set([...taskEvents, 'reminder.fired', 'reminder.cancelled', 'extraction.updated', 'connection.updated'])
  function scheduleReconnect() { app.online = false; const delay = Math.min(30_000, 800 * 2 ** retry++); timer = window.setTimeout(connect, delay) }
  async function connect() { controller?.abort(); controller = new AbortController(); try { const token = localStorage.getItem('campuscue-api-token') || import.meta.env.VITE_API_TOKEN; const response = await fetch('/api/v1/stream', { headers: token ? { Authorization: `Bearer ${token}` } : {}, signal: controller.signal }); if (!response.ok || !response.body) throw new Error(`SSE ${response.status}`); app.online = true; retry = 0; const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''; let eventName = 'message'; let data = ''; while (true) { const { value, done } = await reader.read(); if (done) throw new Error('SSE closed'); buffer += decoder.decode(value, { stream: true }); const lines = buffer.split(/\r?\n/); buffer = lines.pop() || ''; for (const line of lines) { if (line.startsWith('event:')) eventName = line.slice(6).trim(); else if (line.startsWith('data:')) data += line.slice(5).trim(); else if (line === '') { if (allEvents.has(eventName)) { if (taskEvents.has(eventName) || eventName.startsWith('reminder.') || eventName === 'extraction.updated' || eventName === 'connection.updated') refresh() } eventName = 'message'; data = '' } } } } catch (error) { if ((error as Error).name !== 'AbortError') scheduleReconnect() } }
  onMounted(connect); onUnmounted(() => { controller?.abort(); window.clearTimeout(timer) }); return { connect }
}
