import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'
const python = process.env.CAMPUSCUE_PYTHON || path.resolve('..', '.venv-m511fresh', 'Scripts', 'python.exe')
export default defineConfig({ testDir: './tests/e2e', timeout: 30_000, use: { baseURL: 'http://127.0.0.1:4173', trace: 'retain-on-failure', screenshot: 'only-on-failure' }, webServer: [{ command: `"${python}" web/tests/real_backend.py`, cwd: path.resolve('..'), url: 'http://127.0.0.1:6200/api/v1/health', reuseExistingServer: false }, { command: 'npm run dev -- --host 127.0.0.1', url: 'http://127.0.0.1:4173', reuseExistingServer: true }], projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }] })
