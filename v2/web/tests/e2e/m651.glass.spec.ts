import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const token = 'm6-local-test-token'
const evidenceDir = path.resolve('..', '..', '.ai-handoff', 'visual', 'm651', 'glass')

test('captures the real Glass core and verifies material layers', async ({ page }) => {
  fs.mkdirSync(evidenceDir, { recursive: true })
  await page.addInitScript(({ token: initToken }) => localStorage.setItem('campuscue-api-token', initToken), { token })

  const capture = async (route: string, name: string, width: number, fullPage = true) => {
    await page.setViewportSize({ width, height: width < 768 ? 844 : 900 })
    await page.goto(route)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(250)
    await page.screenshot({ path: path.join(evidenceDir, `${name}-${width}.png`), fullPage })
  }

  await capture('/', 'glass-shell', 1440, false)
  await capture('/', 'glass-home', 1440)
  await capture('/tasks', 'glass-tasks', 1440)
  await capture('/agent', 'glass-agent', 1440)
  await capture('/', 'glass-home', 390)
  await capture('/agent', 'glass-agent', 390)

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/agent')
  await page.waitForTimeout(250)
  const material = await page.evaluate(() => {
    const read = (selector: string) => {
      const node = document.querySelector<HTMLElement>(selector)
      if (!node) return null
      const style = getComputedStyle(node)
      return { backgroundColor: style.backgroundColor, backgroundImage: style.backgroundImage, backdropFilter: style.backdropFilter, borderTopColor: style.borderTopColor, boxShadow: style.boxShadow }
    }
    return { shell: read('.agent-shell'), context: read('.agent-context'), composer: read('.chat-composer'), body: getComputedStyle(document.querySelector('.app-shell')!).backgroundImage }
  })
  expect(material.body).toContain('radial-gradient')
  expect(material.shell?.backdropFilter).toContain('blur')
  expect(material.context?.backdropFilter).toContain('blur')
  expect(material.composer?.backdropFilter).toContain('blur')
  expect(material.shell?.boxShadow).toContain('rgba')

  await page.evaluate(() => {
    const workspace = document.querySelector<HTMLElement>('.agent-workspace')
    if (!workspace) return
    workspace.style.position = 'relative'
    for (const [tone, style] of [['blue', 'top:36px;left:8%;background:rgba(61,131,255,.68)'], ['teal', 'top:180px;right:12%;background:rgba(30,194,170,.66)']] as const) {
      const marker = document.createElement('div')
      marker.className = `glass-test-atmosphere-marker ${tone}`
      marker.setAttribute('aria-hidden', 'true')
      marker.style.cssText = `position:absolute;z-index:0;width:240px;height:240px;border-radius:50%;${style};filter:blur(18px);pointer-events:none`
      workspace.prepend(marker)
    }
  })
  await page.screenshot({ path: path.join(evidenceDir, 'glass-agent-marker-1440.png'), fullPage: true })
  await expect(page.locator('.glass-test-atmosphere-marker')).toHaveCount(2)
  await page.evaluate(() => document.querySelector('.app-shell')?.classList.add('glass-no-filter'))
  const fallback = await page.locator('.agent-shell').evaluate(node => {
    const style = getComputedStyle(node)
    return { background: style.background, backgroundImage: style.backgroundImage, backdropFilter: style.backdropFilter }
  })
  expect(fallback.backdropFilter).toBe('none')
  expect(fallback.backgroundImage).toBe('none')
  expect(fallback.background).not.toContain('rgba(0, 0, 0, 0)')
})
