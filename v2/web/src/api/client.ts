import type { Page, Task, TaskWrite, Source, SourceWrite, SourceTest, Message, MessageDetail, Provider, ProviderWrite, ProviderTest, Reminder, Settings, Health, SystemStatus, Logs, Backup, ImportResult } from '../types/api'
const BASE = '/api/v1'
function authHeaders(): Record<string, string> { const token = localStorage.getItem('campuscue-api-token') || import.meta.env.VITE_API_TOKEN; return token ? { Authorization: `Bearer ${token}` } : {} }
export class ApiError extends Error { constructor(public status: number, message: string) { super(message) } }
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init.headers || {}) } })
  if (!response.ok) { let detail = `请求失败（${response.status}）`; try { const body = await response.json(); detail = body.detail || detail } catch {} throw new ApiError(response.status, detail) }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })
export const api = {
  health: () => request<Health>('/health'),
  tasks: (query = '') => request<Page<Task>>(`/tasks${query ? `?${query}` : ''}`),
  createTask: (body: TaskWrite) => request<Task>('/tasks', json(body)),
  updateTask: (id: number, body: unknown) => request<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  completeTask: (id: number) => request<Task>(`/tasks/${id}/complete`, json({})),
  dismissTask: (id: number) => request<Task>(`/tasks/${id}/dismiss`, json({})),
  deleteTask: (id: number) => request<void>(`/tasks/${id}`, { method: 'DELETE' }),
  sources: (query = '') => request<Page<Source>>(`/sources${query ? `?${query}` : ''}`),
  createSource: (body: SourceWrite) => request<Source>('/sources', json(body)),
  updateSource: (id: number, body: SourceWrite) => request<Source>(`/sources/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteSource: (id: number) => request<void>(`/sources/${id}`, { method: 'DELETE' }),
  testSource: (id: number) => request<SourceTest>(`/sources/${id}/test`, json({})),
  messages: (query = '') => request<Page<Message>>(`/messages${query ? `?${query}` : ''}`),
  message: (id: number) => request<MessageDetail>(`/messages/${id}`),
  reminders: (query = '') => request<Page<Reminder>>(`/reminders${query ? `?${query}` : ''}`),
  cancelReminder: (id: number) => request<Reminder>(`/reminders/${id}/cancel`, json({})),
  providers: () => request<Page<Provider>>('/providers'),
  createProvider: (body: ProviderWrite) => request<Provider>('/providers', json(body)),
  updateProvider: (id: number, body: Partial<ProviderWrite>) => request<Provider>(`/providers/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteProvider: (id: number) => request<void>(`/providers/${id}`, { method: 'DELETE' }),
  testProvider: (id: number) => request<ProviderTest>(`/providers/${id}/test`, json({})),
  settings: () => request<Settings>('/settings'),
  updateSettings: (settings: Record<string, unknown>) => request<Settings>('/settings', { method: 'PATCH', body: JSON.stringify({ settings }) }),
  status: () => request<SystemStatus>('/system/status'),
  logs: (query = '') => request<Logs>(`/system/logs${query ? `?${query}` : ''}`),
  backup: () => request<Backup>('/system/backup', json({})),
  restore: (backup: Backup, confirm_replace: boolean) => request<{ restored: boolean; schema_version: number }>('/system/restore', json({ backup, confirm_replace })),
  importTasks: (payload: Record<string, unknown>) => request<ImportResult>('/system/import', json(payload)),
  exportTasks: () => request<{ kind: string; version: number; tasks: Array<Record<string, unknown>> }>('/system/export'),
  agentChat: (body: { source_id: number; conversation_id?: string; message: string }) => request<{ conversation_id: string; message: string; tool_activity: string[] }>('/agent/chat', json(body)),
  threads: () => request<Array<{ conversation_id: string; source_id: number | null; message_count: number; last_activity: number | null }>>('/agent/threads')
}
