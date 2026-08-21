import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import fs from 'node:fs'
import path from 'node:path'

const evidenceDir = path.resolve('..', '..', '.ai-handoff', 'visual', 'm6-final-candidate')
const routes = [
  ['/', 'home'], ['/tasks', 'tasks'], ['/calendar', 'calendar'], ['/messages', 'messages'],
  ['/agent', 'agent'], ['/connections', 'connections'], ['/providers', 'providers'], ['/settings', 'settings'],
] as const
const styles = ['glass', 'dark', 'neumorphism'] as const

async function setStyle(page: import('@playwright/test').Page, style: string) {
  await page.evaluate((value) => {
    localStorage.setItem('campuscue-visual-style', value)
    localStorage.setItem('campuscue-theme', value === 'dark' ? 'dark' : 'light')
  }, style)
}

async function assertNoOverflow(page: import('@playwright/test').Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth && document.body.scrollWidth <= window.innerWidth)).toBeTruthy()
}

test('CampusCue M6 final closure candidate evidence and regression', async ({ page }) => {
  fs.mkdirSync(evidenceDir, { recursive: true })
  for (const folder of ['compare', 'mobile', 'theme']) fs.mkdirSync(path.join(evidenceDir, folder), { recursive: true })
  await page.addInitScript(() => localStorage.setItem('campuscue-api-token', 'm6-local-test-token'))

  const capture = async (route: string, name: string, width: number, style: string, file: string) => {
    await page.setViewportSize({ width, height: width < 768 ? 844 : 900 })
    await page.goto(route)
    await setStyle(page, style)
    await page.reload()
    await expect(page.locator('h1')).toBeVisible()
    await assertNoOverflow(page)
    await page.screenshot({ path: path.join(evidenceDir, file), fullPage: true })
  }

  for (const style of styles) {
    for (const [route, name] of routes) await capture(route, name, 1440, style, `compare/${name}-${style}-1440.png`)
    await capture('/', 'home', 390, style, `mobile/home-${style}-390.png`)
    await capture('/agent', 'agent', 390, style, `mobile/agent-${style}-390.png`)
    await capture('/settings', 'settings', 390, style, style === 'glass' ? 'mobile/settings-theme-selector-390.png' : `mobile/settings-${style}-390.png`)
  }

  for (const width of [1024, 768]) {
    for (const [route] of [['/tasks'], ['/messages'], ['/agent'], ['/settings'], ['/calendar']] as const) {
      await page.setViewportSize({ width, height: 900 }); await page.goto(route); await setStyle(page, 'glass'); await page.reload(); await assertNoOverflow(page)
    }
  }

  await page.emulateMedia({ colorScheme: 'light' }); await page.goto('/settings'); await setStyle(page, 'system'); await page.reload(); await expect(page.locator('html')).toHaveAttribute('data-visual-theme', 'glass'); await expect(page.locator('html')).toHaveAttribute('data-theme', 'light'); await page.screenshot({ path: path.join(evidenceDir, 'theme/system-light-1440.png'), fullPage: true })
  await page.emulateMedia({ colorScheme: 'dark' }); await expect.poll(() => page.locator('html').getAttribute('data-visual-theme')).toBe('dark'); await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark'); await page.screenshot({ path: path.join(evidenceDir, 'theme/system-dark-1440.png'), fullPage: true })
  await page.setViewportSize({ width: 1440, height: 900 }); await page.goto('/settings'); await setStyle(page, 'system'); await page.reload(); await page.screenshot({ path: path.join(evidenceDir, 'theme/theme-selector-1440.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 }); await page.screenshot({ path: path.join(evidenceDir, 'theme/theme-selector-390.png'), fullPage: true })

  for (const style of styles) {
    await page.setViewportSize({ width: 1440, height: 900 }); await page.goto('/'); await setStyle(page, style); await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-visual-theme', style); const homeAxe = await new AxeBuilder({ page }).analyze(); expect(homeAxe.violations).toEqual([])
    await page.goto('/settings'); const settingsAxe = await new AxeBuilder({ page }).analyze(); expect(settingsAxe.violations).toEqual([])
    await page.goto('/agent'); const agentAxe = await new AxeBuilder({ page }).analyze(); expect(agentAxe.violations).toEqual([])
  }

  await page.setViewportSize({ width: 390, height: 844 }); await page.goto('/'); await setStyle(page, 'dark'); await page.reload(); await page.getByRole('button', { name: '更多', exact: true }).click(); await expect(page.getByRole('dialog', { name: '更多' })).toBeVisible(); const sheetAxe = await new AxeBuilder({ page }).analyze(); expect(sheetAxe.violations).toEqual([])
  await page.goto('/tasks'); await page.getByRole('button', { name: '新建任务' }).first().click(); await expect(page.getByRole('dialog')).toBeVisible(); const dialogAxe = await new AxeBuilder({ page }).analyze(); expect(dialogAxe.violations).toEqual([])
})
