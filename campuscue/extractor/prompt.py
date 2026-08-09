"""The L2 extraction prompt.

Kept in its own module because it is a tuned artefact, not incidental string
data: the wording below is what produced 8/8 correct classifications in the
probe run (campuscue/_ark_probe.py), and changing it silently changes the
product's accuracy. Treat edits the way you would treat edits to a model.

The one non-obvious instruction is the last: the model must copy the time phrase
verbatim and must NOT compute a date. Models do that arithmetic in their heads
and get it wrong unauditably; campuscue.extractor.timeresolve does it in code
against the message timestamp instead.
"""

from __future__ import annotations

from datetime import datetime

from campuscue.extractor.timeresolve import CAMPUS_TZ

WEEKDAY_CN = ("一", "二", "三", "四", "五", "六", "日")

SYSTEM_PROMPT = """你是校园事务信息抽取器。输入是一条 QQ 群消息，判断它是否包含需要学生完成的具体事务。

只输出 JSON，不要输出任何其他文字，不要用代码块包裹。

字段说明：
- is_task: 布尔值。是否是需要学生行动的事务通知。闲聊、寒暄、单纯的信息分享、他人之间的对话、对已完成事情的讨论都是 false。
- task_type: homework|exam|competition|activity|notice，is_task 为 false 时填 null
  - homework: 作业、实验报告、论文、课程设计
  - exam: 考试、测验、答辩
  - competition: 比赛、竞赛报名及材料提交
  - activity: 讲座、会议、社团活动、志愿服务
  - notice: 其他需要学生采取行动的通知（缴费、填表、领取材料等）
- title: 用动宾结构概括要做的事，不超过 20 字，如"提交软件工程实验三报告"。is_task 为 false 时填 null
- deadline_phrase: 原文中表示时间的**原始字词**，逐字照抄，如"周五晚上12点前"、"下周二8:30"、"8月10日"。没有提到时间则填 null
- location: 地点原文（教室、提交平台等），没有则 null
- items: 需要携带或提交的物品、材料数组，没有则空数组
- confidence: 0 到 1 的小数，你对 is_task 判断的确信程度。信息含糊、无法确定是否针对全体学生、或不确定是否需要行动时，应低于 0.7
- reason: 一句话说明你为什么这么判断，会直接展示给学生看，要具体

重要规则：
1. deadline_phrase 只照抄原文的时间表述，**绝对不要**自己换算成具体日期。日期换算由程序完成。
2. 如果消息只是在讨论、抱怨、感谢、确认收到，不是布置事务，is_task 必须为 false。
3. 如果消息是某个人对另一个人说的（如"你交了吗"），不是面向全体的通知，is_task 为 false。
4. 宁可把不确定的判为低置信度，也不要编造不存在的截止时间或地点。"""


def build_user_message(
    *,
    text: str,
    sent_at: datetime,
    group_name: str | None = None,
    course_name: str | None = None,
    sender_name: str | None = None,
    sender_role: str | None = None,
) -> str:
    """Frame one message with the context the model needs to judge it.

    The weekday is spelled out alongside the timestamp. Even though the model is
    told not to compute dates, knowing that the message was sent on a Monday
    helps it decide whether "周五" is plausible as a deadline at all, and it makes
    the extraction reproducible when reviewing a stored trace.

    Args:
        text: The raw message body.
        sent_at: When the message was sent (any timezone; rendered in campus time).
        group_name: The group's display name, e.g. "软件工程课程群".
        course_name: The mapped course, when the group is known to be a course
            group -- lets the model expand a bare "实验三" into the right course.
        sender_name: Display name of the sender.
        sender_role: e.g. "任课教师" / "班长" / "同学". Drives how much authority
            the model gives the message.

    Returns:
        The user-role message content.
    """
    local = sent_at.astimezone(CAMPUS_TZ)
    stamp = f"{local:%Y-%m-%d %H:%M} 星期{WEEKDAY_CN[local.weekday()]}"

    lines = []
    if group_name:
        lines.append(f"群名称：{group_name}")
    if course_name:
        lines.append(f"对应课程：{course_name}")
    if sender_name:
        who = f"{sender_name}（{sender_role}）" if sender_role else sender_name
        lines.append(f"发送者：{who}")
    lines.append(f"发送时间：{stamp}")
    lines.append(f"消息内容：{text}")
    return "\n".join(lines)


__all__ = ["SYSTEM_PROMPT", "build_user_message"]
