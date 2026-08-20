# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md。

## 当前（M6.1 WebUI Integration Hardening Checkpoint）

- **M4 FINAL = PASS**（External ChatGPT）
- **M5 FINAL = PASS**（External ChatGPT review completed before M6 authorization）
- **M6 = CHANGES_REQUESTED → M6.1 修复完成**
- **M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**
- **M6 FINAL = NOT YET DECLARED**
- **M7 = NOT_AUTHORIZED**
- 本 checkpoint：完成外部集成审核指出的契约修复；真实 M5 FastAPI/SQLite/RealtimeHub/local fake provider harness、真实命名 SSE、全页面截图和前端 clean build 完成。

## M6.1 修复范围

- Task status 统一为后端 canonical `pending_confirm | pending | done | dismissed`；任务筛选、编辑、删除、截止时间清除、完成/驳回和双提交保护均走真实 API。
- SSE 改为带 Bearer header 的 fetch reader，消费命名事件并以 REST refresh 为 canonical；不把 token 放入 URL。
- Settings 只发送后端允许字段；System status/logs/backup/restore/import/export 已接线。
- Calendar 使用真实 deadline 查询和月导航；Messages/Connections/Providers/Agent source selector 均补齐真实查询或 CRUD/test/delete/toggle flows。
- `v2/web/tests/real_backend.py` 使用隔离 SQLite、真实 M5 composition、确定性 local fake provider upstream；不使用 QQ、真实 API key 或真实 PII。

## 本轮验收（M5 API — PASS）

- FastAPI REST `/api/v1`：Tasks/Sources/Messages/Reminders/Providers/Agent/Settings/System + Health/Status/Logs。
- SSE `/api/v1/stream`：RealtimeHub bounded queue；notifier 注入 TaskService/ReminderService/TaskPipeline；无 replay。
- Schema v3：settings 表、sources.deleted_at 软删除、M5 索引；v1→v2→v3 atomic migration。
- Backup/Restore/Import/Export：逻辑 JSON backup、单事务 restore、V1 `campuscue.tasks` import。
- Auth：loopback 默认无认证；`CAMPUSCUE_REQUIRE_AUTH=1` / 非 loopback 强制 Bearer token。
- Runtime lifecycle：API 最后启动，shutdown 先停 API；API startup failure 进入 rollback。

## M5.1 Final Hardening（Workspace Agent local evidence）

- Finding A PASS：bounded SSE overflow marks a subscriber closed, wakes the active stream, and the generator terminates; disconnect cleanup and normal-subscriber isolation are tested.
- Finding B PASS：`ApiConfig.sse_heartbeat_interval` is passed by `/api/v1/stream`; the route wiring is tested with a short configured interval.
- Finding C PASS：runtime waits for Uvicorn `server.started` with a bounded timeout; Uvicorn startup `SystemExit` is contained in the owned task; occupied-port startup reaches `FAILED` and rolls back API, adapter, bus, and DB.
- Finding D PASS：only `/api/v1/health` is registered; `/api/v1/system/health` is absent from OpenAPI.
- Realtime completeness PASS：task, reminder, extraction and adapter connection producers are present; `connection.updated` crosses the neutral Adapter callback boundary and is tested through the real connection lifecycle.
- Commit ordering PASS：business mutations commit before notification; TaskService, ReminderService and TaskPipeline isolate notifier failures so derived realtime cannot turn a successful mutation into an API failure.

## M5.1.1 Final SSE Route Cleanup

- The `/api/v1/stream` outer generator now unsubscribes in `finally`, covering an HTTP consumer that closes immediately after `: connected` before `RealtimeHub.stream()` enters its own lifecycle.
- Route-level ASGI body-iterator regression confirms early close leaves `subscriber_count() == 0`.

## Verification（Workspace Agent local evidence）

- Full V2 pytest：**488 passed**（fresh installed-package `.venv-m511fresh` non-editable）
- M5/M5.1/M5.1.1 focused：**24 passed**；M5.1.1 new test：**1 passed**
- compileall PASS；Anti-AstrBot PASS；git diff --check PASS；Secret/PII scan PASS
- uvicorn local HTTP smoke PASS（health/task CRUD/reminders/backup）
- Local readiness/SSE smoke PASS；occupied-port startup failure and rollback PASS。
- These are local Workspace Agent results, not independent External ChatGPT execution。
- WebUI `pnpm typecheck` PASS；`pnpm build` PASS；Vitest 2 passed；Playwright full **12 passed**；axe violations 0；截图覆盖 1440 全页面、390 home/tasks/editor/calendar/agent/settings、1024 tasks、768 calendar，见 `.ai-handoff/visual/m61/`。
- Real integration PASS：真实 API task mutation → named SSE → REST refresh；task CRUD/deadline clear/done；calendar navigation；source test；local fake provider test；settings save；export download。

## Known limitation / open design risk

- M4 first-version `(source_id, source_message_id)` uniqueness remains；M5 schema v3 does not change it。
- M3 Task/Reminder cross-repository atomicity remains open design risk; startup `resync_all()` recovery accepted。
- SSE no-replay；断线后 REST refresh canonical state。

## Next gate

External review of M6.1 implementation and evidence is required。M6 FINAL is not declared；M7 remains unauthorized。

## Privacy / safety

- No real QQ IDs, group IDs, chat content, tokens, Provider secrets, or local private paths are recorded here。
- Acceptance used isolated temp DBs; fresh venv and runtime data are not committed。
