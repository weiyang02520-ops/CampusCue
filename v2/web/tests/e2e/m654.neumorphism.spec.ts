import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import fs from 'node:fs'
import path from 'node:path'

const evidenceDir = path.resolve('..', '..', '.ai-handoff', 'visual', 'm654', 'neumorphism')
const tasks = [
  { id:1, title:'提交高数作业', description:null, category:'homework', course:'高等数学', deadline:'2026-08-21T10:00:00Z', status:'pending', priority:'high', confidence:.9, source_id:1, source_message_id:'m-1', source_text_reference:null, created_at:'2026-08-19T08:00:00Z', updated_at:'2026-08-19T08:00:00Z' },
  { id:2, title:'确认迎新志愿者时间', description:null, category:'activity', course:null, deadline:'2026-08-24T04:00:00Z', status:'pending_confirm', priority:'normal', confidence:.9, source_id:1, source_message_id:'m-2', source_text_reference:null, created_at:'2026-08-19T08:00:00Z', updated_at:'2026-08-19T08:00:00Z' },
  { id:3, title:'机器人实验报告', description:null, category:'homework', course:'机器人实验', deadline:'2026-08-25T10:00:00Z', status:'pending', priority:'normal', confidence:.9, source_id:1, source_message_id:'m-3', source_text_reference:null, created_at:'2026-08-19T08:00:00Z', updated_at:'2026-08-19T08:00:00Z' },
]
const source = { id:1, platform:'onebot', conversation_id:'group:campus', name:'校园事务群', enabled:true, auto_extract:true, context_window:5, privacy_policy:'default', created_at:'2026-08-01T00:00:00Z', updated_at:'2026-08-01T00:00:00Z', deleted_at:null }
const message = { id:1, source_id:1, source_message_id:'m-1', created_at:'2026-08-19T08:00:00Z', status:'success', confidence:.9, had_task:true, task_id:1, reason:'识别到明确的校园安排', text_retained:true, retained_text:'请在周五前提交高数作业', normalized_result:null, audit:null, error:null }
const provider = { id:1, name:'校园助手模型', provider_type:'openai_compatible', base_url:'https://api.example.com/v1', model:'campus-small', temperature:.2, max_tokens:800, max_context_tokens:4096, timeout_s:30, secret_reference:'local-key', enabled:true, created_at:'2026-08-01T00:00:00Z', updated_at:'2026-08-01T00:00:00Z' }

async function mockApi(page: import('@playwright/test').Page) {
  let savedTheme = 'light'
  await page.route('**/api/v1/**', async route => {
    const request = route.request(); const url = new URL(request.url()); const apiPath = url.pathname.replace('/api/v1', '')
    if (apiPath === '/stream') return route.fulfill({ status:200, contentType:'text/event-stream', body:': connected\n\n' })
    if (apiPath === '/health') return route.fulfill({ json:{ status:'ok', runtime:'ok', database:'ok', adapter:'ok', reminders:'ok', agent:'ok', api:'ok' } })
    if (apiPath === '/tasks') return route.fulfill({ json:{ items:tasks, total:tasks.length, limit:200, offset:0 } })
    if (apiPath === '/sources') return route.fulfill({ json:{ items:[source], total:1, limit:50, offset:0 } })
    if (apiPath === '/messages') return route.fulfill({ json:{ items:[message], total:1, limit:20, offset:0 } })
    if (apiPath === '/messages/1') return route.fulfill({ json:message })
    if (apiPath === '/reminders') return route.fulfill({ json:{ items:[], total:0, limit:50, offset:0 } })
    if (apiPath === '/providers') return route.fulfill({ json:{ items:[provider], total:1, limit:50, offset:0 } })
    if (apiPath === '/settings' && request.method() === 'PATCH') { savedTheme = (request.postDataJSON() as { settings?: { theme?: string } }).settings?.theme || savedTheme; return route.fulfill({ json:{ settings:{ timezone:'Asia/Shanghai', theme:savedTheme, message_retention_days:30, reminder_default_enabled:true, reminder_min_lead_seconds:60, reminder_quiet_start_hour:23, reminder_quiet_end_hour:8 }, restart_required:[] } }) }
    if (apiPath === '/settings') return route.fulfill({ json:{ settings:{ timezone:'Asia/Shanghai', theme:savedTheme, message_retention_days:30, reminder_default_enabled:true, reminder_min_lead_seconds:60, reminder_quiet_start_hour:23, reminder_quiet_end_hour:8 }, restart_required:[] } })
    if (apiPath === '/system/status') return route.fulfill({ json:{ runtime:'ok', uptime_seconds:42, components:{}, feature_flags:{}, provider_configured:true, adapter_connected:true } })
    if (apiPath === '/system/logs') return route.fulfill({ json:{ items:[] } })
    if (apiPath === '/agent/threads') return route.fulfill({ json:[] })
    if (apiPath === '/agent/chat') return route.fulfill({ json:{ conversation_id:'neu-demo', message:'先完成高数作业，再确认迎新志愿者时间。', tool_activity:[] } })
    return route.fulfill({ json:{} })
  })
}

test.describe('M6.5.4 Neumorphism Stage 1', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => { localStorage.setItem('campuscue-theme','light'); if (!localStorage.getItem('campuscue-visual-style')) localStorage.setItem('campuscue-visual-style','neumorphism') })
    await mockApi(page)
  })

  test('captures the Stage 1 tactile workspace at desktop and mobile sizes', async ({ page }) => {
    fs.mkdirSync(evidenceDir, { recursive:true })
    const capture = async (route: string, name: string, width: number, fullPage = true) => {
      await page.setViewportSize({ width, height:width < 768 ? 844 : 900 }); await page.goto(route); await page.waitForTimeout(240); await expect(page.locator('html')).toHaveAttribute('data-visual-theme','neumorphism'); await page.screenshot({ path:path.join(evidenceDir, `${name}.png`), fullPage }); expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    }
    await capture('/', 'neu-shell-1440', 1440, false); await capture('/', 'neu-home-1440', 1440); await capture('/tasks', 'neu-tasks-1440', 1440); await capture('/agent', 'neu-agent-1440', 1440); await capture('/settings', 'neu-settings-1440', 1440); await capture('/', 'neu-home-390', 390)
    await capture('/agent', 'neu-agent-390', 390, false); await page.locator('.chat-composer').scrollIntoViewIfNeeded(); await page.screenshot({ path:path.join(evidenceDir, 'neu-agent-390.png'), fullPage:false })
  })

  test('enforces tactile material rules and three-style switching', async ({ page }) => {
    const errors:string[] = []; page.on('pageerror', error => errors.push(error.message)); page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) }); await page.setViewportSize({ width:1440, height:900 }); await page.goto('/');
    const material = await page.evaluate(() => ['.app-shell','.sidebar','.today-panel','.focus-panel'].map(selector => { const node = document.querySelector<HTMLElement>(selector); if (!node) return null; const style = getComputedStyle(node); return { selector, image:style.backgroundImage, blur:style.backdropFilter, shadow:style.boxShadow } }))
    for (const surface of material.filter(Boolean)) { expect(surface?.image).toBe('none'); expect(surface?.blur).toBe('none') }
    expect(material.find(item => item?.selector === '.today-panel')?.shadow).toContain('rgba')
    await page.goto('/settings'); await expect(page.getByRole('button', { name:'玻璃拟态' })).toBeVisible(); await expect(page.getByRole('button', { name:'深色界面' })).toBeVisible(); await expect(page.getByRole('button', { name:'新拟态' })).toBeVisible()
    await page.getByRole('button', { name:'深色界面' }).click(); await expect(page.locator('html')).toHaveAttribute('data-visual-theme','dark'); await expect(page.locator('html')).toHaveAttribute('data-theme','dark')
    await page.getByRole('button', { name:'新拟态' }).click(); await expect(page.locator('html')).toHaveAttribute('data-visual-theme','neumorphism'); await page.reload(); await expect(page.locator('html')).toHaveAttribute('data-visual-theme','neumorphism')
    await page.getByRole('button', { name:'玻璃拟态' }).click(); await expect(page.locator('html')).toHaveAttribute('data-visual-theme','glass'); await page.getByRole('button', { name:'新拟态' }).click(); await expect(page.locator('html')).toHaveAttribute('data-visual-theme','neumorphism')
    const axe = await new AxeBuilder({ page }).analyze(); expect(axe.violations).toEqual([]); expect(errors).toEqual([])
  })

  test('captures Stage 2 responsive routes, overlays, and three-material comparisons', async ({ page }) => {
    fs.mkdirSync(evidenceDir, { recursive:true })
    const capture = async (route: string, name: string, width: number, fullPage = true) => {
      await page.setViewportSize({ width, height: width < 768 ? 844 : 900 })
      await page.goto(route)
      await page.waitForTimeout(240)
      await expect(page.locator('html')).toHaveAttribute('data-visual-theme', 'neumorphism')
      await page.screenshot({ path:path.join(evidenceDir, `${name}.png`), fullPage })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    }

    for (const [route, name] of [['/', 'neu-home-1440'], ['/tasks', 'neu-tasks-1440'], ['/calendar', 'neu-calendar-1440'], ['/messages', 'neu-messages-1440'], ['/connections', 'neu-connections-1440'], ['/providers', 'neu-providers-1440'], ['/settings', 'neu-settings-1440']] as const) await capture(route, name, 1440)
    await capture('/agent', 'neu-agent-empty-1440', 1440)
    await page.getByRole('button', { name:'梳理这周截止时间' }).click(); await page.getByRole('button', { name:'发送' }).click(); await expect(page.getByText('先完成高数作业')).toBeVisible(); await page.screenshot({ path:path.join(evidenceDir, 'neu-agent-conversation-1440.png'), fullPage:true })
    await capture('/tasks', 'neu-tasks-1024', 1024); await capture('/calendar', 'neu-calendar-1024', 1024); await capture('/messages', 'neu-messages-1024', 1024); await capture('/agent', 'neu-agent-1024', 1024); await capture('/settings', 'neu-settings-1024', 1024)
    await capture('/tasks', 'neu-tasks-768', 768); await capture('/calendar', 'neu-calendar-768', 768); await capture('/messages', 'neu-messages-768', 768); await capture('/agent', 'neu-agent-768', 768); await capture('/settings', 'neu-settings-768', 768)
    for (const [route, name] of [['/', 'neu-home-390'], ['/tasks', 'neu-tasks-390'], ['/calendar', 'neu-calendar-390'], ['/messages', 'neu-messages-390'], ['/connections', 'neu-connections-390'], ['/providers', 'neu-providers-390'], ['/settings', 'neu-settings-390']] as const) await capture(route, name, 390)
    await capture('/agent', 'neu-agent-empty-390', 390)
    await page.getByRole('button', { name:'梳理这周截止时间' }).click(); await page.getByRole('button', { name:'发送' }).click(); await expect(page.getByText('先完成高数作业')).toBeVisible(); await page.locator('.chat-composer').scrollIntoViewIfNeeded(); await page.screenshot({ path:path.join(evidenceDir, 'neu-agent-conversation-390.png'), fullPage:false })
    await page.goto('/tasks'); await page.getByRole('button', { name:'新建任务' }).click(); await expect(page.getByRole('dialog', { name:'新建任务' })).toBeVisible(); await page.screenshot({ path:path.join(evidenceDir, 'neu-dialog-1440.png'), fullPage:true })
    await page.setViewportSize({ width:390, height:844 }); await page.goto('/'); await page.getByRole('button', { name:'更多' }).click(); await expect(page.getByRole('dialog', { name:'更多' })).toBeVisible(); await page.screenshot({ path:path.join(evidenceDir, 'neu-more-sheet-390.png'), fullPage:false }); await page.getByRole('button', { name:'关闭' }).click().catch(() => {})
    await page.goto('/tasks'); await page.getByRole('button', { name:'新建任务' }).click(); await expect(page.getByRole('dialog', { name:'新建任务' })).toBeVisible(); await page.screenshot({ path:path.join(evidenceDir, 'neu-dialog-390.png'), fullPage:false })
  })

  test('captures Glass, Dark, and Neu comparison pairs at 1440', async ({ page }) => {
    const compareEvidence = path.resolve('..', '..', '.ai-handoff', 'visual', 'm654', 'compare'); fs.mkdirSync(compareEvidence, { recursive:true })
    const routes = [['/', 'home'], ['/tasks', 'tasks'], ['/calendar', 'calendar'], ['/agent', 'agent'], ['/settings', 'settings']] as const
    for (const [route, name] of routes) {
      await page.setViewportSize({ width:1440, height:900 }); await page.goto(route)
      for (const [style, theme] of [['glass', 'light'], ['dark', 'dark'], ['neumorphism', 'light']] as const) {
        await page.evaluate(([nextStyle, nextTheme]) => { localStorage.setItem('campuscue-visual-style', nextStyle); localStorage.setItem('campuscue-theme', nextTheme) }, [style, theme]); await page.reload(); await page.waitForTimeout(220); await expect(page.locator('html')).toHaveAttribute('data-visual-theme', style); await page.screenshot({ path:path.join(compareEvidence, `${name}-${style === 'neumorphism' ? 'neu' : style}-1440.png`), fullPage:true })
      }
    }
  })
})
