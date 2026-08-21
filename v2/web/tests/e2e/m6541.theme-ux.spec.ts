import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import fs from 'node:fs'
import path from 'node:path'

const evidenceDir = path.resolve('..', '..', '.ai-handoff', 'visual', 'm6541')
const tasks = [{ id:1, title:'提交高数作业', description:null, category:'homework', course:'高等数学', deadline:'2026-08-21T10:00:00Z', status:'pending', priority:'high', confidence:.9, source_id:1, source_message_id:'m-1', source_text_reference:null, created_at:'2026-08-19T08:00:00Z', updated_at:'2026-08-19T08:00:00Z' }]
const source = { id:1, platform:'onebot', conversation_id:'group:campus', name:'校园事务群', enabled:true, auto_extract:true, context_window:5, privacy_policy:'default', created_at:'2026-08-01T00:00:00Z', updated_at:'2026-08-01T00:00:00Z', deleted_at:null }
const settings = (theme:string) => ({ timezone:'Asia/Shanghai', theme, message_retention_days:30, reminder_default_enabled:true, reminder_min_lead_seconds:60, reminder_quiet_start_hour:23, reminder_quiet_end_hour:8 })

async function mockApi(page: import('@playwright/test').Page, payloads: Array<Record<string, unknown>>) {
  let backendTheme = 'system'
  await page.route('**/api/v1/**', async route => {
    const request = route.request(); const apiPath = new URL(request.url()).pathname.replace('/api/v1', '')
    if (apiPath === '/stream') return route.fulfill({ status:200, contentType:'text/event-stream', body:': connected\n\n' })
    if (apiPath === '/health') return route.fulfill({ json:{ status:'ok', runtime:'ok', database:'ok', adapter:'ok', reminders:'ok', agent:'ok', api:'ok' } })
    if (apiPath === '/tasks') return route.fulfill({ json:{ items:tasks, total:1, limit:200, offset:0 } })
    if (apiPath === '/sources') return route.fulfill({ json:{ items:[source], total:1, limit:50, offset:0 } })
    if (apiPath === '/messages') return route.fulfill({ json:{ items:[], total:0, limit:20, offset:0 } })
    if (apiPath === '/reminders') return route.fulfill({ json:{ items:[], total:0, limit:50, offset:0 } })
    if (apiPath === '/providers') return route.fulfill({ json:{ items:[], total:0, limit:50, offset:0 } })
    if (apiPath === '/settings' && request.method() === 'PATCH') { const body = request.postDataJSON() as { settings?: Record<string, unknown> }; payloads.push(body.settings || {}); backendTheme = String(body.settings?.theme || backendTheme); return route.fulfill({ json:{ settings:settings(backendTheme), restart_required:[] } }) }
    if (apiPath === '/settings') return route.fulfill({ json:{ settings:settings(backendTheme), restart_required:[] } })
    if (apiPath === '/system/status') return route.fulfill({ json:{ runtime:'ok', provider_configured:false, adapter_connected:false } })
    if (apiPath === '/system/logs') return route.fulfill({ json:{ items:[] } })
    if (apiPath === '/agent/threads') return route.fulfill({ json:[] })
    return route.fulfill({ json:{} })
  })
}

async function prepare(page: import('@playwright/test').Page) {
  await page.addInitScript(() => { localStorage.setItem('campuscue-api-token','m6541-test-token'); if (!localStorage.getItem('campuscue-visual-style')) localStorage.setItem('campuscue-visual-style','system'); if (!localStorage.getItem('campuscue-theme')) localStorage.setItem('campuscue-theme','system') })
}

test.describe('M6.5.4.1 Theme UX semantic cleanup', () => {
  test('resolves System to Glass or Dark without mixed DOM states', async ({ page }) => {
    const payloads: Array<Record<string, unknown>> = []; const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message)); page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
    await prepare(page); await mockApi(page, payloads); await page.emulateMedia({ colorScheme:'light' }); await page.setViewportSize({ width:1440, height:900 }); await page.goto('/settings')
    await expect(page.locator('html')).toHaveAttribute('data-visual-theme','glass'); await expect(page.locator('html')).toHaveAttribute('data-theme','light'); await expect(page.getByText('明暗模式')).toBeHidden(); await expect(page.locator('.appearance-picker')).toBeHidden()
    fs.mkdirSync(evidenceDir, { recursive:true }); await page.screenshot({ path:path.join(evidenceDir,'theme-selector-1440.png'), fullPage:true })
    await page.locator('.visual-style-option').filter({ hasText:'跟随系统' }).click(); await page.getByRole('button', { name:'保存设置' }).click(); await expect.poll(() => payloads.at(-1)?.theme).toBe('system'); await page.goto('/'); await page.screenshot({ path:path.join(evidenceDir,'home-system-light-1440.png'), fullPage:true })
    await page.emulateMedia({ colorScheme:'dark' }); await expect.poll(() => page.locator('html').getAttribute('data-visual-theme')).toBe('dark'); await expect(page.locator('html')).toHaveAttribute('data-theme','dark'); await page.goto('/'); await page.screenshot({ path:path.join(evidenceDir,'home-system-dark-1440.png'), fullPage:true })
    expect(await page.evaluate(() => document.documentElement.dataset.visualTheme === 'dark' && document.documentElement.dataset.theme === 'dark')).toBeTruthy(); expect(errors).toEqual([])
  })

  test('keeps explicit styles stable across OS changes and maps backend payloads', async ({ page }) => {
    const payloads: Array<Record<string, unknown>> = []; const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message)); page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
    await prepare(page); await mockApi(page, payloads); await page.emulateMedia({ colorScheme:'light' }); await page.setViewportSize({ width:1440, height:900 }); await page.goto('/settings')
    const choose = async (label:string) => { await page.locator('.visual-style-option').filter({ hasText:label }).click(); await expect(page.locator('.visual-style-option.active')).toContainText(label) }
    await choose('玻璃拟态'); await expect(page.locator('html')).toHaveAttribute('data-visual-theme','glass'); await expect(page.locator('html')).toHaveAttribute('data-theme','light'); await page.getByRole('button', { name:'保存设置' }).click(); await expect.poll(() => payloads.at(-1)?.theme).toBe('light'); await page.goto('/'); await page.screenshot({ path:path.join(evidenceDir,'home-glass-1440.png'), fullPage:true })
    await page.goto('/settings'); await choose('深色界面'); await expect(page.locator('html')).toHaveAttribute('data-visual-theme','dark'); await expect(page.locator('html')).toHaveAttribute('data-theme','dark'); await page.emulateMedia({ colorScheme:'light' }); await page.reload(); await expect(page.locator('html')).toHaveAttribute('data-visual-theme','dark'); await expect(page.locator('html')).toHaveAttribute('data-theme','dark'); await page.goto('/'); await page.screenshot({ path:path.join(evidenceDir,'home-dark-1440.png'), fullPage:true })
    await page.goto('/settings'); await choose('新拟态'); await expect(page.locator('html')).toHaveAttribute('data-visual-theme','neumorphism'); await expect(page.locator('html')).toHaveAttribute('data-theme','light'); await page.emulateMedia({ colorScheme:'dark' }); await page.reload(); await expect(page.locator('html')).toHaveAttribute('data-visual-theme','neumorphism'); await expect(page.locator('html')).toHaveAttribute('data-theme','light'); await page.getByRole('button', { name:'保存设置' }).click(); await expect.poll(() => payloads.at(-1)?.theme).toBe('light'); await page.goto('/'); await page.screenshot({ path:path.join(evidenceDir,'home-neu-1440.png'), fullPage:true })
    await page.setViewportSize({ width:390, height:844 }); await page.goto('/settings'); await page.screenshot({ path:path.join(evidenceDir,'theme-selector-390.png'), fullPage:true }); const axe = await new AxeBuilder({ page }).analyze(); expect(axe.violations).toEqual([]); expect(payloads.every(payload => payload.theme !== 'neumorphism')).toBeTruthy(); expect(errors).toEqual([])
  })
})
