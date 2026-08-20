import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { Task, TaskStatus } from '../types/api'
export const useTasksStore = defineStore('tasks', () => {
  const items = ref<Task[]>([]); const total = ref(0); const loading = ref(false); const error = ref('')
  async function load(query = '') { loading.value = true; error.value = ''; try { const page = await api.tasks(query); items.value = page.items; total.value = page.total } catch (e) { error.value = e instanceof Error ? e.message : '无法加载任务' } finally { loading.value = false } }
  async function mutate(id: number, action: 'complete' | 'dismiss') { const previous = items.value.find(t => t.id === id); if (!previous) return; const next = { ...previous, status: (action === 'complete' ? 'done' : 'dismissed') as TaskStatus }; items.value = items.value.map(t => t.id === id ? next : t); try { const saved = action === 'complete' ? await api.completeTask(id) : await api.dismissTask(id); items.value = items.value.map(t => t.id === id ? saved : t) } catch (e) { items.value = items.value.map(t => t.id === id ? previous : t); throw e } }
  async function remove(id: number) { const previous = items.value; items.value = previous.filter(t => t.id !== id); try { await api.deleteTask(id) } catch (e) { items.value = previous; throw e } }
  return { items, total, loading, error, load, mutate, remove }
})
