import path from 'node:path'
import { test, expect, type Page } from '@playwright/test'

const source = { id: 1, platform: 'onebot', conversation_id: 'm71-campus', name: '高数课程群', enabled: true, auto_extract: true, context_window: 5, privacy_policy: 'default', created_at: '2026-08-20T00:00:00Z', updated_at: '2026-08-20T00:00:00Z', deleted_at: null }
const task = { id: 1, title: '高等数学第三章作业', description: '明确课程、事项与截止时间', category: 'homework', course: '高等数学', deadline: '2026-08-28T14:00:00Z', status: 'pending', priority: 'normal', confidence: .96, source_id: 1, source_message_id: 'm71-official', source_text_reference: '高等数学第三章作业请于 2026 年 8 月 28 日 22:00 前提交。', created_at: '2026-08-20T00:00:00Z', updated_at: '2026-08-20T00:00:00Z' }
const message = { id: 1, source_id: 1, source_message_id: 'm71-official', created_at: '2026-08-20T00:00:00Z', status: 'success', confidence: .96, had_task: true, task_id: 1, reason: '明确课程、事项与截止时间', text_retained: true, retained_text: task.source_text_reference, normalized_result: { title: task.title, category: 'homework', course: '高等数学', deadline_phrase: '2026年8月28日22:00前', confidence: .96, reason: '明确课程、事项与截止时间' }, audit: { l3: { reason: '明确课程、事项与截止时间' }, l4: { resolved: '2026-08-28T14:00:00Z' }, outcome: { status: 'success', task_id: 1 } }, error: null }

async function mockApi(page: Page, withSource = true) {
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path === '/health') return json({ status:'ok', runtime:'ok', database:'ok', adapter:'ok', reminders:'ok', agent:'ok', api:'ok' })
    if (path === '/sources') return json({ items: withSource ? [source] : [], total: withSource ? 1 : 0, limit:50, offset:0 })
    if (path === '/tasks' || path.startsWith('/tasks?')) return json({ items: withSource ? [task] : [], total: withSource ? 1 : 0, limit:200, offset:0 })
    if (path === '/messages' || path.startsWith('/messages?')) return json({ items: withSource ? [message] : [], total: withSource ? 1 : 0, limit:20, offset:0 })
    if (path.startsWith('/messages/')) return json(message)
    if (path === '/reminders' || path.startsWith('/reminders?')) return json({ items: [], total:0, limit:50, offset:0 })
    if (path === '/providers') return json({ items: [], total:0, limit:50, offset:0 })
    if (path === '/settings') return json({ settings:{ timezone:'Asia/Shanghai', theme:'system', message_retention_days:30, reminder_default_enabled:true, reminder_min_lead_seconds:60, reminder_quiet_start_hour:23, reminder_quiet_end_hour:8 }, restart_required:[] })
    if (path === '/system/status') return json({ runtime:'running', uptime_seconds:10, components:{}, feature_flags:{}, provider_configured:true, adapter_connected:true })
    if (path === '/agent/threads') return json([])
    if (path === '/stream') return route.fulfill({ status:200, headers:{ 'content-type':'text/event-stream' }, body:': connected\n\n' })
    return json({})
  })
}

test.describe('CampusCue M7.1 first-use activation', () => {
  test('M7-A01 M7-A05 shows grounded activation and provenance facts', async ({ page }) => {
    await mockApi(page)
    await page.goto('/')
    await expect(page.getByRole('heading', { name: '5 分钟启动' })).toBeVisible()
    await expect(page.getByText('高数课程群', { exact: false }).first()).toBeVisible()
    await expect(page.getByText('已识别', { exact: false }).first()).toBeVisible()
    await expect(page.getByText('消息引用 m71-official', { exact: false })).toBeVisible()
    await page.screenshot({ path: path.resolve('..', '..', '.ai-handoff', 'evidence', 'm71', 'm71-first-use-home-1440.png'), fullPage: true })
    await page.goto('/messages')
    await expect(page.getByText('明确课程、事项与截止时间', { exact: false }).first()).toBeVisible()
  })

  test('M7-A02 empty activation state explains the next action', async ({ page }) => {
    await mockApi(page, false)
    await page.goto('/')
    await expect(page.getByText('先连接一个消息来源', { exact: false }).first()).toBeVisible()
    await expect(page.getByRole('link', { name: /连接消息源/ }).first()).toBeVisible()
    await page.goto('/connections')
    await page.screenshot({ path: path.resolve('..', '..', '.ai-handoff', 'evidence', 'm71', 'm71-connections-empty-1440.png'), fullPage: true })
  })
})
