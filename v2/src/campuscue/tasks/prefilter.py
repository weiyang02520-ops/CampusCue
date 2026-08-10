"""L1 LocalPrefilter (M2b.1) — clean V2 port of the proven V1 scoring behavior.

Pure function: zero DB, zero Provider, zero AstrBot, deterministic.
Signals: deadline/time/action/affair/authority keywords; threshold ~3.0;
PURE_CHATTER, min/max length guards, Chinese time references, coursework refs.
"""

from __future__ import annotations

import re

from campuscue.tasks.models import PrefilterResult

PASS_THRESHOLD = 3.0
MIN_LENGTH = 4
MAX_LENGTH = 2000

W_DEADLINE = 3.0  # a deadline word alone passes
W_TIME = 3.0  # a time expression alone passes
W_ACTION = 2.0  # action + affair combination passes
W_AFFAIR = 1.5
W_AUTHORITY = 2.5

DEADLINE_WORDS = ("截止", "前交", "交到", "提交截止", "ddl", "deadline", "截至", "过期", "限期")

ACTION_WORDS = ("交", "提交", "上传", "发送", "发到", "填写", "报名", "参加", "完成", "预习", "复习", "打印", "准备", "做")

AFFAIR_WORDS = (
    "作业", "习题", "实验报告", "报告", "论文", "试卷", "考试", "测验", "比赛", "竞赛",
    "报名", "活动", "通知", "截止", "测试", "考核", "课堂展示", "ppt", "PPT",
)

AUTHORITY_WORDS = ("老师", "教授", "班长", "学委", "课代表", "辅导员", "教务处", "通知")

# signals that a message is pure chatter (reject without scoring)
PURE_CHATTER = re.compile(
    r"^(?:"
    r"(?:嗯+|啊+|哦+|哈+|额+|呃+|好|好的|收到|ok|OK|知道|了解|懂|是的|对|同意|赞成|支持)"
    r"|(?:[😀-🙏🌀-🫿✨🎉]|\s)+"
    r"|(?:表情|图片|视频|语音|文件|@)"
    r")+$"
)

# Chinese time expressions that could anchor a deadline
_TIME_RE = re.compile(
    r"(?:今天|明天|明晚|明早|后天|大后天|今晚|昨夜|昨天|前天|"
    r"周[一二三四五六日天]|星期[一二三四五六日天]|礼拜[一二三四五六日天]|"
    r"下?周|下?星期|下?礼拜|本?周末|月底|月初|月底前|"
    r"(?:\d{1,2})\s*月\s*(?:\d{1,2})?\s*日?|"
    r"(?:20\d{2})\s*[-/年]\s*\d{1,2}(?:\s*[-/月]\s*\d{1,2})?|"
    r"\d{1,2}\s*[-/]\s*\d{1,2}|"
    r"(?:上午|下午|晚上|凌晨|中午|傍晚|明早|今晚|明晚|夜里)?\s*\d{1,2}\s*[:：点]\s*\d{0,2}\s*分?"
    r")"
)

# coursework references like "第三章", "P23", "习题5"
_COURSEWORK_RE = re.compile(
    r"(?:第[一二三四五六七八九十百\d]+[章节课讲]|"
    r"(?:p|P|页)\s*\d+|"
    r"习题\s*\d+|"
    r"实验[一二三四五六七八九十\d]+)"
)


def _found(text: str, words: tuple[str, ...]) -> list[str]:
    return [w for w in words if w in text]


def prefilter(text: str) -> PrefilterResult:
    """Score a message. Reasons list explains the decision (auditable)."""
    stripped = text.strip()
    if len(stripped) < MIN_LENGTH:
        return PrefilterResult(passed=False, score=0.0, reasons=["too_short"])
    if len(stripped) > MAX_LENGTH:
        return PrefilterResult(passed=False, score=0.0, reasons=["too_long"])
    if PURE_CHATTER.match(stripped):
        return PrefilterResult(passed=False, score=0.0, reasons=["pure_chatter"])

    score = 0.0
    reasons: list[str] = []

    if deadline := _found(stripped, DEADLINE_WORDS):
        score += W_DEADLINE
        reasons.append(f"deadline:{','.join(deadline)}")
    if times := list(_TIME_RE.finditer(stripped)):
        score += W_TIME
        reasons.append(f"time:{times[0].group()}")
    if actions := _found(stripped, ACTION_WORDS):
        score += W_ACTION
        reasons.append(f"action:{','.join(actions[:2])}")
    if affairs := _found(stripped, AFFAIR_WORDS):
        score += W_AFFAIR
        reasons.append(f"affair:{','.join(affairs[:2])}")
    if authorities := _found(stripped, AUTHORITY_WORDS):
        score += W_AUTHORITY
        reasons.append(f"authority:{','.join(authorities[:2])}")
    if _COURSEWORK_RE.search(stripped):
        score += W_AFFAIR
        reasons.append("coursework")

    return PrefilterResult(passed=score >= PASS_THRESHOLD, score=round(score, 2), reasons=reasons)
