import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const baseTask = { description: null, confidence: .9, source_id: 1, source_text_reference: null, created_at: '2026-08-19T08:00:00Z', updated_at: '2026-08-19T08:00:00Z' }
const seedTasks = [
  { ...baseTask, id: 1, title: '提交高数作业', category: 'homework', course: '高等数学', deadline: '2026-08-21T10:00:00Z', status: 'pending', priority: 'high', source_message_id: 'm-1' },
  { ...baseTask, id: 2, title: '确认迎新志愿者时间', category: 'activity', course: null, deadline: '2026-08-24T04:00:00Z', status: 'pending_confirm', priority: 'normal', source_message_id: 'm-2' },
  { ...baseTask, id: 3, title: '机器人实验报告', category: 'homework', course: '机器人实验', deadline: '2026-08-25T10:00:00Z', status: 'pending', priority: 'normal', source_message_id: 'm-3' },
  { ...baseTask, id: 4, title: '英语四级模拟考试', category: 'exam', course: '大学英语', deadline: '2026-08-27T03:00:00Z', status: 'pending', priority: 'normal', source_message_id: 'm-4' },
  { ...baseTask, id: 5, title: '智能组周会', category: 'activity', course: null, deadline: null, status: 'done', priority: 'low', source_message_id: 'm-5' },
]
const sources = [1, 2, 3].map((id) => ({ id, platform: 'onebot', conversation_id: `group:campus-${id}`, name: ['校园事务群', '学习小组', '社团通知'][id - 1], enabled: true, auto_extract: id !== 3, context_window: 5, privacy_policy: 'default', created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-01T00:00:00Z', deleted_at: null }))
const messages = [1, 2, 3].map((id) => ({ id, source_id: id, source_message_id: `m-${id}`, created_at: `2026-08-${19 + id}T08:00:00Z`, status: 'success', confidence: .88 + id / 100, had_task: true, task_id: id, reason: '识别到明确的校园安排', text_retained: true, retained_text: ['请在周五前提交高数作业', '请确认迎新志愿时间', '机器人实验报告下周一交'][id - 1], normalized_result: null, audit: null, error: null }))
const provider = { id: 1, name: '校园助手模型', provider_type: 'openai_compatible', base_url: 'https://api.example.com/v1', model: 'campus-small', temperature: .2, max_tokens: 800, max_context_tokens: 4096, timeout_s: 30, secret_reference: 'local-key', enabled: true, created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-01T00:00:00Z' }
async function mockApi(page: import('@playwright/test').Page) {
  const tasks = structuredClone(seedTasks)
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()); const path = url.pathname.replace('/api/v1', '')
    if (path === '/stream') return route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'event: task.updated\ndata: {"id":1}\n\n' })
    if (path === '/health') return route.fulfill({ json: { status:'ok', runtime:'ok', database:'ok', adapter:'ok', reminders:'ok', agent:'ok', api:'ok' } })
    if (path === '/tasks' && route.request().method() === 'GET') { const status = url.searchParams.get('status'); const items = status ? tasks.filter(task => task.status === status) : tasks; return route.fulfill({ json: { items, total: items.length, limit: 200, offset: 0 } }) }
    if (path === '/tasks' && route.request().method() === 'POST') return route.fulfill({ status: 201, json: { ...tasks[0], id: 99, title: '新建校园任务' } })
    const action = path.match(/^\/tasks\/(\d+)\/(complete|dismiss)$/)
    if (action) { const task = tasks.find(item => item.id === Number(action[1])); if (task) task.status = action[2] === 'complete' ? 'done' : 'dismissed'; return route.fulfill({ json: { ...task } }) }
    const messageDetail = path.match(/^\/messages\/(\d+)$/); if (messageDetail) return route.fulfill({ json: messages.find(message => message.id === Number(messageDetail[1])) || messages[0] })
    if (path === '/sources') return route.fulfill({ json: { items:sources, total:sources.length, limit:50, offset:0 } })
    if (path === '/providers') return route.fulfill({ json: { items:[provider], total:1, limit:50, offset:0 } })
    if (path === '/messages') return route.fulfill({ json: { items:messages, total:messages.length, limit:20, offset:0 } })
    if (path === '/reminders') return route.fulfill({ json: { items:[], total:0, limit:50, offset:0 } })
    if (path === '/settings') return route.fulfill({ json: { settings: { timezone:'Asia/Shanghai', theme:'light', message_retention_days:30, reminder_default_enabled:true, reminder_min_lead_seconds:60, reminder_quiet_start_hour:23, reminder_quiet_end_hour:8 }, restart_required:[] } })
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
  test('supports task completion and agent chat', async ({ page }) => { await page.getByRole('link', { name:'任务' }).first().click(); await expect(page.getByRole('heading', { name:'提交高数作业' })).toBeVisible(); await page.getByRole('button', { name:'完成任务：提交高数作业' }).click(); await page.locator('.segmented').getByRole('button', { name:'已完成' }).click(); await expect(page.getByTestId('task-1')).toHaveClass(/task-done/); await page.getByRole('link', { name:'AI 助手' }).first().click(); await page.getByRole('button', { name:'梳理这周截止时间' }).click(); await page.getByRole('button', { name:'发送' }).click(); await expect(page.getByText('这周优先完成高数作业')).toBeVisible() })
  test('opens advanced task filters and collapsible context', async ({ page }) => { await page.goto('/tasks'); await page.getByRole('button', { name:'筛选' }).click(); await expect(page.getByRole('dialog', { name:'筛选任务' })).toBeVisible(); await page.keyboard.press('Escape'); await expect(page.getByRole('dialog', { name:'筛选任务' })).toBeHidden(); await page.goto('/agent'); await expect(page.getByRole('button', { name:'隐藏上下文' })).toBeVisible(); await page.getByRole('button', { name:'隐藏上下文' }).click(); await expect(page.locator('.agent-context')).toHaveCount(0); await page.getByRole('button', { name:'显示上下文' }).click(); await expect(page.locator('.agent-context')).toBeVisible() })
  test('uses a messages master-detail workspace', async ({ page }) => { await page.goto('/messages'); await expect(page.locator('.message-inspector')).toBeVisible(); await expect(page.getByText('关联任务')).toBeVisible() })
  test('moves filters and context into mobile sheets', async ({ page }) => { await page.setViewportSize({ width: 390, height: 844 }); await page.goto('/tasks'); await page.getByRole('button', { name:'筛选' }).click(); await expect(page.getByRole('dialog', { name:'筛选任务' })).toBeVisible(); await page.keyboard.press('Escape'); await page.goto('/agent'); await page.getByRole('button', { name:'上下文' }).click(); await expect(page.getByRole('dialog', { name:'当前上下文' })).toBeVisible() })
  test('passes accessibility scan on the main route', async ({ page }) => { const results = await new AxeBuilder({ page }).analyze(); expect(results.violations).toEqual([]) })
  test('keeps the visual dataset balanced', async ({ page }) => { await page.goto('/tasks'); await expect(page.locator('.task-row')).toHaveCount(5); await page.goto('/messages'); await expect(page.locator('.message-card')).toHaveCount(3); await page.goto('/connections'); await expect(page.locator('.connection-card')).toHaveCount(3); await page.goto('/providers'); await expect(page.locator('.provider-card')).toHaveCount(1) })
  test('opens More navigation on mobile and closes after navigation', async ({ page }) => { await page.setViewportSize({ width: 390, height: 844 }); await page.reload(); const more = page.getByRole('button', { name:'更多' }); await more.click(); await expect(page.getByRole('dialog', { name:'更多' })).toBeVisible(); await page.getByRole('dialog', { name:'更多' }).getByRole('link', { name:'设置' }).click(); await expect(page.locator('h1')).toHaveText('设置'); await expect(more).toHaveClass(/active/); await more.click(); await page.getByRole('dialog', { name:'更多' }).getByRole('link', { name:'连接' }).click(); await expect(page.locator('h1')).toHaveText('连接') })
  test('deep links all product areas', async ({ page }) => { for (const [path, heading] of [['/calendar', '日历'], ['/messages', '消息'], ['/connections', '连接'], ['/providers', '模型提供商'], ['/settings', '设置']]) { await page.goto(path); await expect(page.locator('h1')).toHaveText(heading) } })
  for (const width of [390, 599, 768, 1024, 1440]) test(`responsive screenshot ${width}`, async ({ page }) => { await page.setViewportSize({ width, height: width < 768 ? 844 : 900 }); await page.reload(); await expect(page.getByRole('heading', { name:'总览' })).toBeVisible(); await page.screenshot({ path: `test-results/m6-${width}.png`, fullPage: true }) })
})
