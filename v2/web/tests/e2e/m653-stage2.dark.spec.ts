import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve('..', '..')
const darkEvidence = path.join(root, '.ai-handoff', 'visual', 'm653-stage2', 'dark')
const compareEvidence = path.join(root, '.ai-handoff', 'visual', 'm653-stage2', 'compare')
const baseTask = { description: null, confidence: .9, source_id: 1, source_text_reference: null, created_at: '2026-08-19T08:00:00Z', updated_at: '2026-08-19T08:00:00Z' }
const tasks = [
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
  let settingTheme = 'dark'
  await page.route('**/api/v1/**', async route => {
    const request = route.request(); const url = new URL(request.url()); const apiPath = url.pathname.replace('/api/v1', '')
    if (apiPath === '/stream') return route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': connected\n\n' })
    if (apiPath === '/health') return route.fulfill({ json: { status:'ok', runtime:'ok', database:'ok', adapter:'ok', reminders:'ok', agent:'ok', api:'ok' } })
    if (apiPath === '/tasks' && request.method() === 'GET') return route.fulfill({ json: { items: tasks, total: tasks.length, limit: 200, offset: 0 } })
    if (apiPath === '/tasks' && request.method() === 'POST') return route.fulfill({ status:201, json: { ...tasks[0], id:99, title:'新建校园任务' } })
    const action = apiPath.match(/^\/tasks\/(\d+)\/(complete|dismiss)$/); if (action) return route.fulfill({ json: tasks.find(item => item.id === Number(action[1])) || tasks[0] })
    const messageDetail = apiPath.match(/^\/messages\/(\d+)$/); if (messageDetail) return route.fulfill({ json: messages.find(message => message.id === Number(messageDetail[1])) || messages[0] })
    if (apiPath === '/sources') return route.fulfill({ json: { items:sources, total:sources.length, limit:50, offset:0 } })
    if (apiPath === '/providers') return route.fulfill({ json: { items:[provider], total:1, limit:50, offset:0 } })
    if (apiPath === '/messages') return route.fulfill({ json: { items:messages, total:messages.length, limit:20, offset:0 } })
    if (apiPath === '/reminders') return route.fulfill({ json: { items:[], total:0, limit:50, offset:0 } })
    if (apiPath === '/settings' && request.method() === 'PATCH') { const body = request.postDataJSON() as { settings?: { theme?: string } }; settingTheme = body.settings?.theme || settingTheme; return route.fulfill({ json: { settings: { timezone:'Asia/Shanghai', theme:settingTheme, message_retention_days:30, reminder_default_enabled:true, reminder_min_lead_seconds:60, reminder_quiet_start_hour:23, reminder_quiet_end_hour:8 }, restart_required:[] } }) }
    if (apiPath === '/settings') return route.fulfill({ json: { settings: { timezone:'Asia/Shanghai', theme:settingTheme, message_retention_days:30, reminder_default_enabled:true, reminder_min_lead_seconds:60, reminder_quiet_start_hour:23, reminder_quiet_end_hour:8 }, restart_required:[] } })
    if (apiPath === '/system/status') return route.fulfill({ json: { runtime:'ok', uptime_seconds:42, components:{}, feature_flags:{}, provider_configured:true, adapter_connected:true } })
    if (apiPath === '/system/logs') return route.fulfill({ json: { items:[{ level:'info', message:'消息通道已连接' }] } })
    if (apiPath === '/agent/threads') return route.fulfill({ json: [] })
    if (apiPath === '/agent/chat') return route.fulfill({ json: { conversation_id:'demo', message:'这周优先完成高数作业，再确认志愿者时间。', tool_activity:['读取本周任务'] } })
    if (apiPath.match(/^\/sources\/\d+\/test$/)) return route.fulfill({ json:{ ok:true, reachable:true, latency_ms:42, error_category:null, message:'连接正常' } })
    if (apiPath.match(/^\/providers\/\d+\/test$/)) return route.fulfill({ json:{ ok:true, latency_ms:58, error_category:null, message:'连接正常' } })
    return route.fulfill({ json:{} })
  })
}

test.describe('M6.5.3 Dark UI Stage 2', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => { localStorage.setItem('campuscue-api-token', 'm6-local-test-token'); if (!localStorage.getItem('campuscue-theme')) localStorage.setItem('campuscue-theme', 'dark') })
    await mockApi(page)
  })

  test('captures the required dark responsive evidence', async ({ page }) => {
    fs.mkdirSync(darkEvidence, { recursive:true })
    const capture = async (route: string, name: string, width: number, fullPage = true) => {
      await page.setViewportSize({ width, height: width < 768 ? 844 : 900 }); await page.goto(route); await page.waitForTimeout(260); await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark'); await page.screenshot({ path:path.join(darkEvidence, `${name}.png`), fullPage }); expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    }
    for (const [route, name] of [['/', 'dark-home-1440'], ['/tasks', 'dark-tasks-1440'], ['/calendar', 'dark-calendar-1440'], ['/messages', 'dark-messages-1440'], ['/connections', 'dark-connections-1440'], ['/providers', 'dark-providers-1440'], ['/settings', 'dark-settings-1440']] as const) await capture(route, name, 1440)
    await capture('/agent', 'dark-agent-empty-1440', 1440); await page.getByRole('button', { name:'梳理这周截止时间' }).click(); await page.getByRole('button', { name:'发送' }).click(); await expect(page.getByText('这周优先完成高数作业')).toBeVisible(); await page.screenshot({ path:path.join(darkEvidence, 'dark-agent-conversation-1440.png'), fullPage:true })
    for (const [route, name] of [['/tasks', 'dark-tasks-1024'], ['/calendar', 'dark-calendar-1024'], ['/messages', 'dark-messages-1024'], ['/agent', 'dark-agent-1024'], ['/settings', 'dark-settings-1024']] as const) await capture(route, name, 1024)
    for (const [route, name] of [['/', 'dark-home-390'], ['/tasks', 'dark-tasks-390'], ['/calendar', 'dark-calendar-390'], ['/messages', 'dark-messages-390'], ['/connections', 'dark-connections-390'], ['/providers', 'dark-providers-390'], ['/settings', 'dark-settings-390']] as const) await capture(route, name, 390)
    await capture('/agent', 'dark-agent-empty-390', 390); await page.getByRole('button', { name:'梳理这周截止时间' }).click(); await page.getByRole('button', { name:'发送' }).click(); await expect(page.getByText('这周优先完成高数作业')).toBeVisible(); await page.locator('.chat-composer').scrollIntoViewIfNeeded(); await page.screenshot({ path:path.join(darkEvidence, 'dark-agent-conversation-390.png'), fullPage:false })
  })

  test('captures dialog and bottom sheet states with system-theme semantics', async ({ page }) => {
    fs.mkdirSync(darkEvidence, { recursive:true }); await page.setViewportSize({ width:1440, height:900 }); await page.goto('/tasks'); await page.getByRole('button', { name:'新建任务' }).click(); await expect(page.getByRole('dialog', { name:'新建任务' })).toBeVisible(); await page.screenshot({ path:path.join(darkEvidence, 'dark-dialog-1440.png'), fullPage:true })
    await page.setViewportSize({ width:390, height:844 }); await page.goto('/'); await page.getByRole('button', { name:'更多' }).click(); await expect(page.getByRole('dialog', { name:'更多' })).toBeVisible(); await page.screenshot({ path:path.join(darkEvidence, 'dark-more-sheet-390.png'), fullPage:false })
    await page.emulateMedia({ colorScheme:'dark' }); await page.goto('/settings'); await page.getByRole('button', { name:'跟随系统' }).click(); await page.getByRole('button', { name:'保存设置' }).click(); await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await page.emulateMedia({ colorScheme:'light' }); await expect.poll(() => page.locator('html').getAttribute('data-theme')).toBe('light'); await page.reload(); await expect(page.locator('html')).toHaveAttribute('data-theme', 'light'); await expect(page.locator('.appearance-picker button.active')).toHaveText('跟随系统')
    const axe = await new AxeBuilder({ page }).analyze(); expect(axe.violations).toEqual([])
  })

  test('keeps dark surfaces solid and responsive routes free of errors', async ({ page }) => {
    const errors:string[] = []; page.on('pageerror', error => errors.push(error.message)); page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) }); await page.setViewportSize({ width:1440, height:900 }); await page.goto('/agent');
    const material = await page.evaluate(() => ['.app-shell','.agent-shell','.agent-context','.chat-composer','.dialog-backdrop'].map(selector => { const node = document.querySelector<HTMLElement>(selector); if (!node) return null; const style = getComputedStyle(node); return { selector, image:style.backgroundImage, blur:style.backdropFilter } }))
    for (const surface of material.filter(Boolean)) { expect(surface?.image).toBe('none'); expect(surface?.blur).toBe('none') }
    for (const route of ['/','/tasks','/calendar','/messages','/connections','/providers','/settings','/agent']) { await page.goto(route); expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy() }
    expect(errors).toEqual([])
  })

  test('captures Glass and Dark comparison pairs at 1440', async ({ page }) => {
    fs.mkdirSync(compareEvidence, { recursive:true }); const routes = [['/', 'home'], ['/tasks', 'tasks'], ['/calendar', 'calendar'], ['/messages', 'messages'], ['/agent', 'agent'], ['/settings', 'settings']] as const
    for (const [route, name] of routes) { await page.setViewportSize({ width:1440, height:900 }); await page.goto(route); await page.evaluate(() => localStorage.setItem('campuscue-theme', 'light')); await page.reload(); await page.waitForTimeout(220); await page.screenshot({ path:path.join(compareEvidence, `${name}-glass-1440.png`), fullPage:true }); await page.evaluate(() => localStorage.setItem('campuscue-theme', 'dark')); await page.reload(); await page.waitForTimeout(220); await page.screenshot({ path:path.join(compareEvidence, `${name}-dark-1440.png`), fullPage:true }) }
  })
})
