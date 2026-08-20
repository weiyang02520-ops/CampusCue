import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import fs from 'node:fs'
import path from 'node:path'

const token = 'm6-local-test-token'
const evidenceDir = path.resolve('..', '..', '.ai-handoff', 'visual', 'm652', 'glass')
const tasks = [
  { id: 1, title: '提交高数作业', description: null, category: 'homework', course: '高等数学', deadline: '2026-08-21T10:00:00Z', status: 'pending', priority: 'high', confidence: .9, source_id: 1, source_message_id: 'm-1', source_text_reference: null, created_at: '2026-08-19T08:00:00Z', updated_at: '2026-08-19T08:00:00Z' },
  { id: 2, title: '确认迎新志愿者时间', description: null, category: 'activity', course: null, deadline: '2026-08-24T04:00:00Z', status: 'pending_confirm', priority: 'normal', confidence: .9, source_id: 1, source_message_id: 'm-2', source_text_reference: null, created_at: '2026-08-19T08:00:00Z', updated_at: '2026-08-19T08:00:00Z' },
  { id: 3, title: '机器人实验报告', description: null, category: 'homework', course: '机器人实验', deadline: '2026-08-25T10:00:00Z', status: 'pending', priority: 'normal', confidence: .9, source_id: 1, source_message_id: 'm-3', source_text_reference: null, created_at: '2026-08-19T08:00:00Z', updated_at: '2026-08-19T08:00:00Z' },
]
const sources = [{ id: 1, platform: 'onebot', conversation_id: 'group:campus', name: '校园事务群', enabled: true, auto_extract: true, context_window: 5, privacy_policy: 'default', created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-01T00:00:00Z', deleted_at: null }]
const messages = [{ id: 1, source_id: 1, source_message_id: 'm-1', created_at: '2026-08-19T08:00:00Z', status: 'success', confidence: .9, had_task: true, task_id: 1, reason: '识别到明确的校园安排', text_retained: true, retained_text: '请在周五前提交高数作业' }]

async function mockApi(page: import('@playwright/test').Page) {
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const apiPath = url.pathname.replace('/api/v1', '')
    if (apiPath === '/stream') return route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': connected\n\n' })
    if (apiPath === '/health') return route.fulfill({ json: { status: 'ok', runtime: 'ok', database: 'ok', adapter: 'ok', reminders: 'ok', agent: 'ok', api: 'ok' } })
    if (apiPath === '/tasks') return route.fulfill({ json: { items: tasks, total: tasks.length, limit: 200, offset: 0 } })
    if (apiPath === '/sources') return route.fulfill({ json: { items: sources, total: 1, limit: 50, offset: 0 } })
    if (apiPath === '/messages') return route.fulfill({ json: { items: messages, total: 1, limit: 20, offset: 0 } })
    if (apiPath === '/providers') return route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 } })
    if (apiPath === '/settings') return route.fulfill({ json: { settings: { timezone: 'Asia/Shanghai', theme: 'light', message_retention_days: 30, reminder_default_enabled: true, reminder_min_lead_seconds: 60, reminder_quiet_start_hour: 23, reminder_quiet_end_hour: 8 }, restart_required: [] } })
    return route.fulfill({ json: {} })
  })
}

test.describe('M6.5.2 Glass refinement', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(({ initToken }) => localStorage.setItem('campuscue-api-token', initToken), { initToken: token })
    await mockApi(page)
  })

  test('captures Stage 1 refinement evidence and validates material tiers', async ({ page }) => {
    fs.mkdirSync(evidenceDir, { recursive: true })
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })

    const capture = async (route: string, name: string, width: number) => {
      await page.setViewportSize({ width, height: width < 768 ? 844 : 900 })
      await page.goto(route)
      await page.waitForLoadState('domcontentloaded')
      await page.waitForTimeout(250)
      await page.screenshot({ path: path.join(evidenceDir, `${name}-${width}.png`), fullPage: true })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    }

    await capture('/', 'refine-home', 1440)
    await capture('/tasks', 'refine-tasks', 1440)
    await capture('/agent', 'refine-agent', 1440)
    await capture('/', 'refine-home', 390)
    await capture('/agent', 'refine-agent', 390)

    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/agent')
    const material = await page.evaluate(() => {
      const read = (selector: string) => {
        const element = document.querySelector<HTMLElement>(selector)
        if (!element) return null
        const style = getComputedStyle(element)
        return { background: style.backgroundColor, blur: style.backdropFilter, shadow: style.boxShadow }
      }
      return { shell: read('.agent-shell'), context: read('.agent-context'), composer: read('.chat-composer'), controls: read('.agent-head-actions'), atmosphere: getComputedStyle(document.querySelector('.app-shell')!).backgroundImage }
    })
    expect(material.atmosphere).toContain('radial-gradient')
    expect(material.shell?.blur).toContain('blur')
    expect(material.context?.blur).toContain('blur')
    expect(material.composer?.blur).toContain('blur')
    expect(material.controls?.blur).toContain('blur')
    expect(material.shell?.shadow).toContain('rgba')
    expect(await page.locator('.agent-shell .prompt-chips .prompt-primary').count()).toBe(1)
    expect(await page.locator('.agent-shell .prompt-chips button').count()).toBe(4)

    await page.goto('/tasks')
    await expect(page.locator('.next-deadline')).not.toContainText('T')
    await expect(page.locator('.next-deadline')).not.toContainText('Z')
    const axe = await new AxeBuilder({ page }).analyze()
    expect(axe.violations).toEqual([])
    expect(errors).toEqual([])
  })

  test('keeps theme persistence and local fallback behavior intact', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: '切换深色模式' }).click()
    await expect.poll(() => page.locator('html').getAttribute('data-theme')).toBe('dark')
    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await page.getByRole('button', { name: '切换浅色模式' }).click()
    await page.goto('/agent')
    await page.locator('.app-shell').evaluate(node => node.classList.add('glass-no-filter'))
    const fallback = await page.locator('.agent-shell').evaluate(node => {
      const style = getComputedStyle(node)
      return { backgroundImage: style.backgroundImage, backdropFilter: style.backdropFilter, background: style.background }
    })
    expect(fallback.backdropFilter).toBe('none')
    expect(fallback.backgroundImage).toBe('none')
    expect(fallback.background).not.toContain('rgba(0, 0, 0, 0)')
  })
})
