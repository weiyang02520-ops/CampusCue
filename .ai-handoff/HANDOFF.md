# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md。

## 当前（M5 API + Realtime Checkpoint）

- **M4 FINAL = PASS**（External ChatGPT）
- **M5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**
- **M5.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**
- **M5 FINAL = NOT YET DECLARED**
- **M6 = NOT_AUTHORIZED**
- 本 checkpoint：M5 API + Realtime 最终封口、测试、fresh installed package、本地 HTTP/SSE smoke 完成。

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

## Verification（Workspace Agent local evidence）

- Full V2 pytest：**487 passed**（fresh installed-package `.venv-m51fresh` non-editable）
- M5/M5.1 focused：**23 passed**；M5.1 new tests：**7 passed**
- compileall PASS；Anti-AstrBot PASS；git diff --check PASS；Secret/PII scan PASS
- uvicorn local HTTP smoke PASS（health/task CRUD/reminders/backup）
- Local readiness/SSE smoke PASS；occupied-port startup failure and rollback PASS。
- These are local Workspace Agent results, not independent External ChatGPT execution。

## Known limitation / open design risk

- M4 first-version `(source_id, source_message_id)` uniqueness remains；M5 schema v3 does not change it。
- M3 Task/Reminder cross-repository atomicity remains open design risk; startup `resync_all()` recovery accepted。
- SSE no-replay；断线后 REST refresh canonical state。

## Next gate

External ChatGPT independent review of the pushed M5.1 checkpoint。M5 FINAL is not declared；M6 remains unauthorized。

## Privacy / safety

- No real QQ IDs, group IDs, chat content, tokens, Provider secrets, or local private paths are recorded here。
- Acceptance used isolated temp DBs; fresh venv and runtime data are not committed。
