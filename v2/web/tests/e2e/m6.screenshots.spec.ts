import { test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const token = 'm6-local-test-token'
const evidenceDir = path.resolve('..', '..', '.ai-handoff', 'visual', process.env.M6_SCREENSHOT_DIR || 'm64')

test('captures M6.1 page and responsive evidence', async ({ page }) => {
  fs.mkdirSync(evidenceDir, { recursive: true })
  await page.addInitScript(({ token: initToken, dark }) => { localStorage.setItem('campuscue-api-token', initToken); if (dark) localStorage.setItem('campuscue-theme', 'dark') }, { token, dark: process.env.M6_DARK === '1' })

  const capture = async (route: string, name: string, width: number, height = 900) => {
    await page.setViewportSize({ width, height })
    await page.goto(route)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(250)
    await page.screenshot({ path: path.join(evidenceDir, `${name}-${width}.png`), fullPage: true })
  }

  for (const [route, name] of [
    ['/', 'home'],
    ['/tasks', 'tasks'],
    ['/messages', 'messages'],
    ['/calendar', 'calendar'],
    ['/agent', 'agent'],
    ['/connections', 'connections'],
    ['/providers', 'providers'],
    ['/settings', 'settings'],
  ] as const) {
    await capture(route, name, 1440)
  }

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/agent')
  await page.getByRole('button', { name: '查看今天安排' }).click()
  await page.getByRole('button', { name: '发送' }).click()
  await page.locator('.chat-message.assistant').last().waitFor({ state: 'visible', timeout: 10000 })
  await page.screenshot({ path: path.join(evidenceDir, 'agent-conversation-1440.png'), fullPage: true })

  await capture('/', 'home', 390, 844)
  await capture('/tasks', 'tasks', 390, 844)
  await capture('/messages', 'messages', 390, 844)
  await page.goto('/tasks')
  await page.getByRole('button', { name: '新建任务' }).first().click()
  await page.screenshot({ path: path.join(evidenceDir, 'tasks-editor-390.png'), fullPage: true })
  await page.getByRole('button', { name: '取消' }).click()
  await page.getByRole('button', { name: '更多', exact: true }).click()
  await page.screenshot({ path: path.join(evidenceDir, 'mobile-more-390.png'), fullPage: true })
  await page.getByRole('dialog', { name: '更多' }).getByRole('link', { name: '设置' }).click()
  await page.screenshot({ path: path.join(evidenceDir, 'settings-from-more-390.png'), fullPage: true })
  await capture('/calendar', 'calendar', 390, 844)
  await capture('/agent', 'agent', 390, 844)
  await page.getByRole('button', { name: '查看今天安排' }).click()
  await page.getByRole('button', { name: '发送' }).click()
  await page.locator('.chat-message.assistant').last().waitFor({ state: 'visible', timeout: 10000 })
  await page.screenshot({ path: path.join(evidenceDir, 'agent-conversation-390.png'), fullPage: true })
  await capture('/settings', 'settings', 390, 844)
  await capture('/tasks', 'tasks', 1024)
  await capture('/calendar', 'calendar', 768)
})
