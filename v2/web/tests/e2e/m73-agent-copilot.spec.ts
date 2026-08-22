import path from 'node:path'
import { test, expect, type Page, type Route } from '@playwright/test'

const source = { id: 1, platform: 'onebot', conversation_id: 'm73-demo-group', name: '高数课程群', enabled: true, auto_extract: true, context_window: 5, privacy_policy: 'default', created_at: '2026-08-20T00:00:00Z', updated_at: '2026-08-20T00:00:00Z', deleted_at: null }
const task = { id: 1, title: '高等数学第三章作业', description: null, category: 'homework', course: '高等数学', deadline: '2026-08-28T14:00:00Z', status: 'pending', priority: 'normal', confidence: .96, source_id: 1, source_message_id: 'm73-demo-message', source_text_reference: null, created_at: '2026-08-20T00:00:00Z', updated_at: '2026-08-20T00:00:00Z' }

async function mockApi(page: Page, scheduled = false) {
  await page.route('**/api/v1/**', async (route: Route) => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path === '/sources') return json({ items: [source], total: 1, limit: 50, offset: 0 })
    if (path === '/tasks' || path.startsWith('/tasks?')) return json({ items: [task], total: 1, limit: 200, offset: 0 })
    if (path === '/agent/threads') return json([{ conversation_id: 'm73-thread', source_id: 1, message_count: 2, last_activity: 1 }])
    if (path === '/agent/chat') {
      const body = JSON.parse(route.request().postData() || '{}')
      if (body.message === '确认') return json({ conversation_id: 'm73-thread', message: '已更新任务，提醒已重新安排。', tool_activity: ['已修改任务'], confirmation_state: 'confirmed' })
      if (body.message === '取消') return json({ conversation_id: 'm73-thread', message: '已取消，这次不会修改任务。', tool_activity: ['已取消待确认操作'], confirmation_state: 'cancelled' })
      return json({ conversation_id: 'm73-thread', message: '准备修改「高等数学第三章作业」：截止时间→2026年8月29日22:00。确认吗？', tool_activity: ['已查看任务详情', '等待确认：修改任务'], confirmation_state: 'pending' })
    }
    if (path === '/health') return json({ status: 'ok', runtime: 'ok', database: 'ok', adapter: 'ok', reminders: 'ok', agent: 'ok', api: 'ok' })
    if (path === '/reminders' || path.startsWith('/reminders?')) return json({ items: scheduled ? [{ id: 1, task_id: 1, trigger_at: '2026-08-28T14:00:00Z', type: 'deadline', status: 'scheduled', last_run: null, error: null, created_at: '2026-08-20T00:00:00Z', updated_at: '2026-08-20T00:00:00Z' }] : [], total: scheduled ? 1 : 0, limit: 50, offset: 0 })
    if (path === '/messages' || path.startsWith('/messages?')) return json({ items: [], total: 0, limit: 20, offset: 0 })
    if (path === '/settings') return json({ settings: { timezone: 'Asia/Shanghai', theme: 'system', message_retention_days: 30, reminder_default_enabled: true, reminder_min_lead_seconds: 60, reminder_quiet_start_hour: 23, reminder_quiet_end_hour: 8 }, restart_required: [] })
    if (path === '/providers') return json({ items: [], total: 0, limit: 50, offset: 0 })
    if (path === '/system/status') return json({ runtime: 'running', uptime_seconds: 10, components: {}, feature_flags: {}, provider_configured: true, adapter_connected: true })
    if (path === '/stream') return route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream' }, body: ': connected\n\n' })
    return json({})
  })
}

test('M7-A08 Agent shows actual activity and requires explicit confirmation', async ({ page }) => {
  await mockApi(page)
  await page.goto('/agent')
  await page.screenshot({ path: path.resolve('..', '..', '.ai-handoff', 'evidence', 'm73', 'm73-agent-read-1440.png'), fullPage: true })
  await page.getByLabel('对 AI 助手说').fill('把高数作业截止时间改到周六晚上10点')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText('这是一次写入操作')).toBeVisible()
  await expect(page.getByText('已查看任务详情')).toBeVisible()
  await expect(page.getByRole('button', { name: '确认' })).toBeVisible()
  await page.screenshot({ path: path.resolve('..', '..', '.ai-handoff', 'evidence', 'm73', 'm73-agent-confirm-1440.png'), fullPage: true })
  await page.getByRole('button', { name: '确认' }).click()
  await expect(page.getByText('已更新任务，提醒已重新安排。')).toBeVisible()
  await page.screenshot({ path: path.resolve('..', '..', '.ai-handoff', 'evidence', 'm73', 'm73-agent-confirmed-1440.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: path.resolve('..', '..', '.ai-handoff', 'evidence', 'm73', 'm73-agent-confirm-390.png'), fullPage: true })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await page.screenshot({ path: path.resolve('..', '..', '.ai-handoff', 'evidence', 'm73', 'm73-five-minute-home-1440.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: path.resolve('..', '..', '.ai-handoff', 'evidence', 'm73', 'm73-final-home-390.png'), fullPage: true })
})

test('scheduled reminder copy does not promise external delivery in Noop mode', async ({ page }) => {
  await mockApi(page, true)
  await page.goto('/')
  await expect(page.getByText('提醒已计划，等待触发。')).toBeVisible()
  await expect(page.getByText('届时会按来源发送', { exact: false })).toHaveCount(0)
})
