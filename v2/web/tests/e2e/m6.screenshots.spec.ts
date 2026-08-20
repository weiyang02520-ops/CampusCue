import { test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const token = 'm6-local-test-token'
const evidenceDir = path.resolve('..', '..', '.ai-handoff', 'visual', 'm61')

test('captures M6.1 page and responsive evidence', async ({ page }) => {
  fs.mkdirSync(evidenceDir, { recursive: true })
  await page.addInitScript(value => localStorage.setItem('campuscue-api-token', value), token)

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

  await capture('/', 'home', 390, 844)
  await capture('/tasks', 'tasks', 390, 844)
  await page.getByRole('button', { name: '新建任务' }).click()
  await page.screenshot({ path: path.join(evidenceDir, 'tasks-editor-390.png'), fullPage: true })
  await page.getByRole('button', { name: '取消' }).click()
  await capture('/calendar', 'calendar', 390, 844)
  await capture('/agent', 'agent', 390, 844)
  await capture('/settings', 'settings', 390, 844)
  await capture('/tasks', 'tasks', 1024)
  await capture('/calendar', 'calendar', 768)
})
