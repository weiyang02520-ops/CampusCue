import { test, expect, type Page, type Route } from '@playwright/test'

const source = { id: 1, platform: 'onebot', conversation_id: '24680', name: '高数课程群', enabled: true, auto_extract: true, context_window: 5, privacy_policy: 'default', created_at: '2026-08-20T00:00:00Z', updated_at: '2026-08-20T00:00:00Z', deleted_at: null }
const task = { id: 1, title: '高等数学第三章作业', description: null, category: 'homework', course: '高等数学', deadline: '2026-08-28T14:00:00Z', status: 'pending', priority: 'normal', confidence: .96, source_id: 1, source_message_id: 'm72-reminder', source_text_reference: null, created_at: '2026-08-20T00:00:00Z', updated_at: '2026-08-20T00:00:00Z' }
const message = { id: 1, source_id: 1, source_message_id: 'm72-reminder', created_at: '2026-08-20T00:00:00Z', status: 'success', confidence: .96, had_task: true, task_id: 1, reason: '明确课程、事项与截止时间', text_retained: false, retained_text: null }

async function mockApi(page: Page, reminderError: string | null = null) {
  await page.route('**/api/v1/**', async (route: Route) => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path === '/sources') return json({ items: [source], total: 1, limit: 50, offset: 0 })
    if (path === '/sources/1/test') return json({ ok: false, reachable: false, latency_ms: null, error_category: 'disconnected', message: 'adapter not connected' })
    if (path === '/tasks' || path.startsWith('/tasks?')) return json({ items: [task], total: 1, limit: 200, offset: 0 })
    if (path === '/messages' || path.startsWith('/messages?')) return json({ items: [message], total: 1, limit: 20, offset: 0 })
    if (path === '/reminders' || path.startsWith('/reminders?')) return json({ items: [{ id: 1, task_id: 1, trigger_at: '2026-08-28T14:00:00Z', type: 'deadline', status: reminderError ? 'fired' : 'scheduled', last_run: reminderError ? '2026-08-28T14:00:00Z' : null, error: reminderError, created_at: '2026-08-20T00:00:00Z', updated_at: '2026-08-20T00:00:00Z' }], total: 1, limit: 50, offset: 0 })
    if (path === '/settings') return json({ settings: { timezone: 'Asia/Shanghai', theme: 'system', message_retention_days: 30, reminder_default_enabled: true, reminder_min_lead_seconds: 60, reminder_quiet_start_hour: 23, reminder_quiet_end_hour: 8 }, restart_required: [] })
    if (path === '/providers') return json({ items: [], total: 0, limit: 50, offset: 0 })
    if (path === '/agent/threads') return json([{ conversation_id: 'm72-thread', source_id: 1, message_count: 2, last_activity: 1 }])
    if (path === '/health') return json({ status: 'ok', runtime: 'ok', database: 'ok', adapter: 'ok', reminders: 'ok', agent: 'ok', api: 'ok' })
    if (path === '/system/status') return json({ runtime: 'running', uptime_seconds: 10, components: {}, feature_flags: {}, provider_configured: true, adapter_connected: true })
    if (path === '/stream') return route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream' }, body: ': connected\n\n' })
    return json({})
  })
}

test('M7.2 reminder failure is visible and activation follows a real Agent thread', async ({ page }) => {
  await mockApi(page, 'delivery:adapter_disconnected')
  await page.goto('/')
  await expect(page.getByText('4/4')).toBeVisible()
  await expect(page.getByText('提醒发送失败', { exact: false })).toBeVisible()
  await page.goto('/connections')
  await page.getByRole('button', { name: '测试连接' }).click()
  await expect(page.getByText('自检失败', { exact: false })).toBeVisible()
  await expect(page.getByText('adapter not connected', { exact: false })).toBeVisible()
})
