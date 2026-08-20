# CampusCue WebUI

M6 WebUI for CampusCue V2. The app is a Vue 3 + TypeScript + Vite workspace with Vue Router, Pinia, and Lucide icons.

## Local development

```text
pnpm install
pnpm dev
```

Vite proxies `/api` to `http://127.0.0.1:6200`. REST loads canonical state, while `/api/v1/stream` only triggers refreshes after realtime notifications. The Agent view renders `tool_activity` only when the M5 response includes actual entries.

## Verification

```text
pnpm typecheck
pnpm build
pnpm test:unit
pnpm test:e2e
```

Playwright covers the home workspace, task completion, Agent chat, deep links, axe accessibility checks, and responsive screenshots at 390, 599, 768, 1024, and 1440 pixels.
