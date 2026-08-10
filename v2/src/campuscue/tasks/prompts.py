"""Task extraction prompt (M2b.1). Provider-neutral system instruction."""

from __future__ import annotations

from campuscue.tasks.models import EXTRACTION_JSON_SCHEMA

SYSTEM_PROMPT = """你是校园事务提取器。从群聊消息中判断是否存在校园事务（作业/考试/比赛/活动/通知），并提取结构化信息。

规则：
1. 只有明确提到截止时间、提交要求、考试安排、比赛报名等事务性内容时，has_task 才为 true。
2. title 要简洁（如"第三章作业"），不要包含冗余修饰。
3. course 是课程名（如"高等数学"）；无法确定时为 null。
4. deadline_phrase 保留原始时间表达原文（如"周五晚上12点前"），不做换算。
5. submission_method 是提交方式（如"学习通"）；无则 null。
6. confidence 是 0-1 的浮点数，表示你对该消息确实是校园事务的把握。
7. reason 用一句话说明判断依据。
8. 纯闲聊、无事务内容时 has_task 必须为 false。

输出 JSON 必须符合以下 schema：
{schema}
"""


def build_system_prompt() -> str:
    import json

    return SYSTEM_PROMPT.format(schema=json.dumps(EXTRACTION_JSON_SCHEMA, ensure_ascii=False, indent=2))


def build_user_message(*, current_text: str, context_lines: list[str], message_time: str) -> str:
    parts: list[str] = []
    if context_lines:
        parts.append("此前相关消息（仅作上下文参考）：")
        for line in context_lines:
            parts.append(f"- {line}")
        parts.append("")
    parts.append(f"当前消息（消息时间 {message_time}）：")
    parts.append(current_text)
    return "\n".join(parts)


# Strict JSON-only fallback prompt (used when endpoint rejects json_schema)
FALLBACK_PROMPT = """你是校园事务提取器。只输出一个 JSON 对象，不要输出任何其他文字、解释或 markdown 代码块标记。
必须包含字段：has_task(boolean), category(字符串, 可选 homework/exam/competition/activity/notice/other), title(字符串), course(字符串或null), deadline_phrase(字符串或null), submission_method(字符串或null), confidence(0-1数字), reason(字符串)。
当前消息：{message}"""
