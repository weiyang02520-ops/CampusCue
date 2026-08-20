import type { Page, Task, Source, Message, Provider, Reminder, Settings, Health } from '../types/api'
const BASE = '/api/v1'
export class ApiError extends Error { constructor(public status: number, message: string) { super(message) } }
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(init.headers || {}) } })
  if (!response.ok) { let detail = `请求失败（${response.status}）`; try { const body = await response.json(); detail = body.detail || detail } catch {} throw new ApiError(response.status, detail) }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })
export const api = {
  health: () => request<Health>('/health'),
  tasks: (query = '') => request<Page<Task>>(`/tasks${query ? `?${query}` : ''}`),
  createTask: (body: unknown) => request<Task>('/tasks', json(body)),
  updateTask: (id: number, body: unknown) => request<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  completeTask: (id: number) => request<Task>(`/tasks/${id}/complete`, json({})),
  dismissTask: (id: number) => request<Task>(`/tasks/${id}/dismiss`, json({})),
  deleteTask: (id: number) => request<void>(`/tasks/${id}`, { method: 'DELETE' }),
  sources: () => request<Page<Source>>('/sources'),
  createSource: (body: unknown) => request<Source>('/sources', json(body)),
  updateSource: (id: number, body: unknown) => request<Source>(`/sources/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteSource: (id: number) => request<void>(`/sources/${id}`, { method: 'DELETE' }),
  testSource: (id: number) => request<{ ok: boolean; message: string }>(`/sources/${id}/test`, json({})),
  messages: (query = '') => request<Page<Message>>(`/messages${query ? `?${query}` : ''}`),
  reminders: (query = '') => request<Page<Reminder>>(`/reminders${query ? `?${query}` : ''}`),
  cancelReminder: (id: number) => request<Reminder>(`/reminders/${id}/cancel`, json({})),
  providers: () => request<Page<Provider>>('/providers'),
  createProvider: (body: unknown) => request<Provider>('/providers', json(body)),
  updateProvider: (id: number, body: unknown) => request<Provider>(`/providers/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteProvider: (id: number) => request<void>(`/providers/${id}`, { method: 'DELETE' }),
  testProvider: (id: number) => request<{ ok: boolean; message: string }>(`/providers/${id}/test`, json({})),
  settings: () => request<Settings>('/settings'),
  updateSettings: (settings: Record<string, unknown>) => request<Settings>('/settings', { method: 'PATCH', body: JSON.stringify({ settings }) }),
  agentChat: (body: { source_id: number; conversation_id?: string; message: string }) => request<{ conversation_id: string; message: string; tool_activity: string[] }>('/agent/chat', json(body)),
  threads: () => request<Array<{ conversation_id: string; source_id: number | null; message_count: number; last_activity: number | null }>>('/agent/threads')
}
