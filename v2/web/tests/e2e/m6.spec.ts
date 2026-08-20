import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const seedTasks = [
  { id: 1, title: '提交高数作业', description: null, category: 'homework', course: '高等数学', deadline: '2026-08-21T10:00:00Z', status: 'pending', priority: 'high', confidence: .95, source_id: 1, source_message_id: 'm-1', source_text_reference: null, created_at: '2026-08-19T08:00:00Z', updated_at: '2026-08-19T08:00:00Z' },
  { id: 2, title: '确认迎新志愿者时间', description: null, category: 'activity', course: null, deadline: '2026-08-24T04:00:00Z', status: 'pending', priority: 'normal', confidence: .87, source_id: 1, source_message_id: 'm-2', source_text_reference: null, created_at: '2026-08-19T09:00:00Z', updated_at: '2026-08-19T09:00:00Z' }
]
const source = { id: 1, platform: 'onebot', conversation_id: 'group:campus', name: '校园事务群', enabled: true, auto_extract: true, context_window: 5, privacy_policy: 'default', created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-01T00:00:00Z', deleted_at: null }
async function mockApi(page: import('@playwright/test').Page) {
  const tasks = structuredClone(seedTasks)
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()); const path = url.pathname.replace('/api/v1', '')
    if (path === '/stream') return route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'event: task.updated\ndata: {"id":1}\n\n' })
    if (path === '/health') return route.fulfill({ json: { status:'ok', runtime:'ok', database:'ok', adapter:'ok', reminders:'ok', agent:'ok', api:'ok' } })
    if (path === '/tasks' && route.request().method() === 'GET') { const status = url.searchParams.get('status'); const items = status ? tasks.filter(task => task.status === status) : tasks; return route.fulfill({ json: { items, total: items.length, limit: 50, offset: 0 } }) }
    if (path === '/tasks' && route.request().method() === 'POST') return route.fulfill({ status: 201, json: { ...tasks[0], id: 99, title: '新建校园任务' } })
    const action = path.match(/^\/tasks\/(\d+)\/(complete|dismiss)$/)
    if (action) { const task = tasks.find(item => item.id === Number(action[1])); if (task) task.status = action[2] === 'complete' ? 'done' : 'dismissed'; return route.fulfill({ json: { ...task } }) }
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
  test.beforeEach(async ({ page }) => { await mockApi(page); await page.goto('/') })
  test('renders the home workspace without horizontal overflow', async ({ page }) => { await expect(page.getByRole('heading', { name:'总览' })).toBeVisible(); await expect(page.getByText('本周焦点')).toBeVisible(); expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy() })
  test('derives the home date from the current clock', async ({ page }) => { await page.addInitScript({ content: `(() => { const NativeDate = Date; const fixed = NativeDate.parse('2026-08-21T08:00:00+08:00'); class FixedDate extends NativeDate { constructor(...args) { super(args.length ? args[0] : fixed) } static now() { return fixed } } window.Date = FixedDate })()` }); await page.reload(); await expect(page.getByText('星期五，8 月 21 日')).toBeVisible(); await expect(page.locator('.week-line .week-active')).toHaveText('五') })
  test('keeps Home completion and dismissal as separate requests', async ({ page }) => { const requests: string[] = []; page.on('request', request => { if (request.method() === 'POST') requests.push(new URL(request.url()).pathname) }); await page.getByRole('button', { name:'完成任务：提交高数作业' }).click(); await expect.poll(() => requests).toContain('/api/v1/tasks/1/complete'); await page.getByRole('button', { name:'忽略任务：确认迎新志愿者时间' }).click(); await expect.poll(() => requests).toContain('/api/v1/tasks/2/dismiss') })
  test('supports task completion and agent chat', async ({ page }) => { await page.getByRole('link', { name:'任务' }).first().click(); await expect(page.getByText('提交高数作业')).toBeVisible(); await page.getByRole('button', { name:'完成任务：提交高数作业' }).click(); await page.locator('.segmented').getByRole('button', { name:'已完成' }).click(); await expect(page.getByTestId('task-1')).toHaveClass(/task-done/); await page.getByRole('link', { name:'AI 助手' }).first().click(); await page.getByRole('button', { name:'梳理这周截止时间' }).click(); await page.getByRole('button', { name:'发送' }).click(); await expect(page.getByText('这周优先完成高数作业')).toBeVisible() })
  test('opens More navigation on mobile and closes after navigation', async ({ page }) => { await page.setViewportSize({ width: 390, height: 844 }); await page.reload(); const more = page.getByRole('button', { name:'更多' }); await more.click(); await expect(page.getByRole('dialog', { name:'更多' })).toBeVisible(); await page.getByRole('dialog', { name:'更多' }).getByRole('link', { name:'设置' }).click(); await expect(page.locator('h1')).toHaveText('设置'); await expect(more).toHaveClass(/active/); await more.click(); await page.getByRole('dialog', { name:'更多' }).getByRole('link', { name:'连接' }).click(); await expect(page.locator('h1')).toHaveText('连接') })
  test('passes accessibility scan on the main route', async ({ page }) => { const results = await new AxeBuilder({ page }).analyze(); expect(results.violations).toEqual([]) })
  test('deep links all product areas', async ({ page }) => { for (const [path, heading] of [['/calendar', '日历'], ['/messages', '消息'], ['/connections', '连接'], ['/providers', '模型提供商'], ['/settings', '设置']]) { await page.goto(path); await expect(page.locator('h1')).toHaveText(heading) } })
  for (const width of [390, 599, 768, 1024, 1440]) test(`responsive screenshot ${width}`, async ({ page }) => { await page.setViewportSize({ width, height: width < 768 ? 844 : 900 }); await page.reload(); await expect(page.getByRole('heading', { name:'总览' })).toBeVisible(); await page.screenshot({ path: `test-results/m6-${width}.png`, fullPage: true }) })
})
