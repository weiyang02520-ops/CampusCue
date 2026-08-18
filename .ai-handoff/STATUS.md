# STATUS.md

> 当前状态摘要。详细内容见 canonical HANDOFF.md 与 PROJECT_STATE.md。

- 阶段：**M4.2 REAL PROVIDER TOOL CALL CHECKPOINT（PASS，QQ E2E 待下一门）**
- **M3 FINAL = PASS**
- **M4.1 STATIC HARDENING = PASS**
- **M4 = REAL_PROVIDER_TOOL_CALL_PASS_QQ_E2E_PENDING**
- **M4 FINAL = NOT YET DECLARED**
- **M5 = NOT_AUTHORIZED**
- Real Provider Tool Call：**PASS**（provider_type=openai_compatible，model=deepseek-chat，真实 httpx transport；模型自主发出 `task_list` tool call → ToolRegistry → TaskService → 临时真实 SQLite → tool result → 第二次真实 Provider 调用 → 最终回答反映合成 DB 数据；改数据后回答随之变化；Source 作用域隔离验证通过；无 mock、无硬编码分发）
- 暴露并修复的真实兼容性 bug：真实 DeepSeek 在 tool-call 轮次同时返回辅助 content + tool_calls，原解析硬判 MALFORMED_OUTPUT → 最小修复（tool_calls 权威，辅助文本丢弃）
- Real QQ Agent E2E：**NEXT GATE，NOT RUN**
- QQ processes / protected primary account：**NOT TOUCHED**
- Workspace Agent local verification：full V2 **466 passed**（fresh `.venv-m42fresh` installed-package）；focused M4 **88 passed**；compileall PASS；Anti-AstrBot PASS；git diff --check PASS；fresh import origin PASS
- Known limitation：M4 first-version `(source_id, source_message_id)` uniqueness means one Agent user message can create at most one Task；second `task_create` returns safe failure。M3 cross-repository Task/Reminder atomicity remains an open design risk; startup `resync_all()` recovery is accepted。
