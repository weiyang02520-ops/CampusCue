import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const tasks = [
  { id: 1, title: '提交高数作业', description: null, category: 'assignment', course: '高等数学', deadline: '2026-08-21T10:00:00Z', status: 'pending', priority: 'high', confidence: .95, source_id: 1, source_message_id: 'm-1', source_text_reference: null, created_at: '2026-08-19T08:00:00Z', updated_at: '2026-08-19T08:00:00Z' },
  { id: 2, title: '确认迎新志愿者时间', description: null, category: 'event', course: null, deadline: '2026-08-24T04:00:00Z', status: 'pending', priority: 'normal', confidence: .87, source_id: 1, source_message_id: 'm-2', source_text_reference: null, created_at: '2026-08-19T09:00:00Z', updated_at: '2026-08-19T09:00:00Z' }
]
const source = { id: 1, platform: 'onebot', conversation_id: 'group:campus', name: '校园事务群', enabled: true, auto_extract: true, context_window: 5, privacy_policy: 'default', created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-01T00:00:00Z', deleted_at: null }
async function mockApi(page: import('@playwright/test').Page) {
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()); const path = url.pathname.replace('/api/v1', '')
    if (path === '/stream') return route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': connected\n\n' })
    if (path === '/health') return route.fulfill({ json: { status:'ok', runtime:'ok', database:'ok', adapter:'ok', reminders:'ok', agent:'ok', api:'ok' } })
    if (path === '/tasks' && route.request().method() === 'GET') return route.fulfill({ json: { items: tasks, total: tasks.length, limit: 50, offset: 0 } })
    if (path === '/tasks' && route.request().method() === 'POST') return route.fulfill({ status: 201, json: { ...tasks[0], id: 99, title: '新建校园任务' } })
    if (path.match(/^\/tasks\/\d+\/(complete|dismiss)$/)) return route.fulfill({ json: { ...tasks[0], status: path.endsWith('complete') ? 'completed' : 'dismissed' } })
    if (path === '/sources') return route.fulfill({ json: { items:[source], total:1, limit:50, offset:0 } })
    if (path === '/providers') return route.fulfill({ json: { items:[], total:0, limit:50, offset:0 } })
    if (path === '/messages') return route.fulfill({ json: { items:[], total:0, limit:20, offset:0 } })
    if (path === '/reminders') return route.fulfill({ json: { items:[], total:0, limit:50, offset:0 } })
    if (path === '/settings') return route.fulfill({ json: { settings: { timezone:'Asia/Shanghai' }, restart_required:[] } })
    if (path === '/agent/chat') return route.fulfill({ json: { conversation_id:'demo', message:'这周优先完成高数作业，再确认志愿者时间。', tool_activity:[] } })
    if (path === '/agent/threads') return route.fulfill({ json: [] })
    return route.fulfill({ json: {} })
  })
}

test.describe('M6 web workspace', () => {
  test.beforeEach(async ({ page }) => { await page.addInitScript(() => { class StableEventSource { onopen: (() => void) | null = null; onerror: (() => void) | null = null; onmessage: ((event: MessageEvent) => void) | null = null; constructor(public url: string) { setTimeout(() => this.onopen?.(), 0) } close() {} addEventListener() {} removeEventListener() {} } ; (window as unknown as { EventSource: typeof StableEventSource }).EventSource = StableEventSource }); await mockApi(page); await page.goto('/') })
  test('renders the home workspace without horizontal overflow', async ({ page }) => { await expect(page.getByRole('heading', { name:'总览' })).toBeVisible(); await expect(page.getByText('本周焦点')).toBeVisible(); expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy() })
  test('supports task completion and agent chat', async ({ page }) => { await page.getByRole('link', { name:'任务' }).first().click(); await expect(page.getByText('提交高数作业')).toBeVisible(); await page.getByRole('button', { name:'完成任务：提交高数作业' }).click(); await page.getByRole('button', { name:'全部' }).click(); await expect(page.getByTestId('task-1')).toHaveClass(/task-completed/); await page.getByRole('link', { name:'AI 助手' }).first().click(); await page.getByRole('button', { name:'梳理这周截止时间' }).click(); await page.getByRole('button', { name:'发送' }).click(); await expect(page.getByText('这周优先完成高数作业')).toBeVisible() })
  test('passes accessibility scan on the main route', async ({ page }) => { const results = await new AxeBuilder({ page }).analyze(); expect(results.violations).toEqual([]) })
  test('deep links all product areas', async ({ page }) => { for (const [path, heading] of [['/calendar', '日历'], ['/messages', '消息'], ['/connections', '连接'], ['/providers', '模型提供商'], ['/settings', '设置']]) { await page.goto(path); await expect(page.locator('h1')).toHaveText(heading) } })
  for (const width of [390, 599, 768, 1024, 1440]) test(`responsive screenshot ${width}`, async ({ page }) => { await page.setViewportSize({ width, height: width < 768 ? 844 : 900 }); await page.reload(); await expect(page.getByRole('heading', { name:'总览' })).toBeVisible(); await page.screenshot({ path: `test-results/m6-${width}.png`, fullPage: true }) })
})
