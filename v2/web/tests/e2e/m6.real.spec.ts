import { test, expect } from '@playwright/test'
const token = 'm6-local-test-token'
test.describe('M6.1 real M5 integration', () => {
  test.beforeEach(async ({ page }) => { await page.addInitScript(value => localStorage.setItem('campuscue-api-token', value), token); await page.goto('/') })
  test('loads real API data and refreshes after a real SSE mutation', async ({ page }) => {
    await expect(page.getByText('M6 seeded deadline')).toBeVisible(); await page.goto('/tasks');
    const response = await page.request.post('/api/v1/tasks', { headers:{ Authorization:`Bearer ${token}` }, data:{ title:'External SSE task', category:'competition', priority:'normal' } }); expect(response.ok()).toBeTruthy();
    await expect(page.getByText('External SSE task')).toBeVisible({ timeout: 8000 });
  })
  test('runs task CRUD, real calendar, connections, provider test, settings, and data actions', async ({ page }) => {
    await page.goto('/tasks'); await page.getByRole('button', { name:'新建任务' }).click(); await page.getByLabel('标题').fill('Real create task'); await page.getByLabel('类型').selectOption('competition'); await page.getByLabel('截止时间').fill('2030-08-20T12:00'); await page.getByRole('button', { name:'保存任务' }).click(); await expect(page.getByText('Real create task')).toBeVisible();
    await page.getByRole('button', { name:'编辑任务：Real create task' }).click(); await page.getByLabel('截止时间').fill(''); await page.getByRole('button', { name:'保存任务' }).click(); await page.getByRole('button', { name:'完成任务：Real create task' }).click(); await page.locator('.segmented').getByRole('button', { name:'已完成' }).click(); await expect(page.getByTestId(/task-/).filter({ hasText:'Real create task' })).toBeVisible();
    await page.goto('/calendar'); await expect(page.getByText('M6 seeded deadline')).toBeVisible(); await page.getByRole('button', { name:'下个月' }).click(); await page.getByRole('button', { name:'上个月' }).click();
    await page.goto('/connections'); await page.getByRole('button', { name:'添加连接' }).click(); await page.getByLabel('会话标识').fill('m6-created-source'); await page.getByRole('button', { name:'保存连接' }).click(); await expect(page.getByRole('heading', { name:'m6-created-source' })).toBeVisible(); await page.getByRole('button', { name:/测试连接/ }).last().click();
    await page.goto('/providers'); await page.getByRole('button', { name:'添加提供商' }).click(); const providerDialog = page.getByRole('dialog', { name:'添加模型提供商' }); await providerDialog.getByLabel('名称').fill('Local fake provider'); await providerDialog.getByLabel('模型').fill('fake'); await providerDialog.getByLabel('Base URL').fill('http://127.0.0.1:6397/v1'); await providerDialog.getByRole('button', { name:'保存提供商' }).click(); await expect(page.getByText('Local fake provider')).toBeVisible(); await page.getByRole('button', { name:'测试' }).click(); await expect(page.getByText(/连接通过/)).toBeVisible();
    await page.goto('/settings'); await page.getByLabel('消息保留天数').fill('60'); await page.getByRole('button', { name:'保存设置' }).click(); await expect(page.getByText('设置已保存')).toBeVisible(); const download = page.waitForEvent('download'); await page.getByRole('button', { name:'导出任务' }).click(); await (await download).path();
  })
})
