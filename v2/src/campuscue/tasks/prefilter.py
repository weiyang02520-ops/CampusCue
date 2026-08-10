"""L1 MessageHygieneFilter + L1.5 LocalSignalAnalyzer (M2b.1 AI-first).

AI-FIRST POLICY (ADR-013): local deterministic code is NOT the semantic gate.
- MessageHygieneFilter: only VERY high-certainty invalid content may hard-drop
  (empty, whitespace, oversized, system noise). Subjective reasons like
  "not enough keywords" are forbidden.
- LocalSignalAnalyzer: pure-function hints (deadline/time/action/affair/...).
  score is metadata ONLY — it never decides whether the LLM is called.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MIN_TEXT_LENGTH = 1
MAX_TEXT_LENGTH = 2000


@dataclass(frozen=True)
class HygieneResult:
    passed: bool
    reason: str = ""  # deterministic reason only


@dataclass(frozen=True)
class LocalSignals:
    score: float = 0.0
    tags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ Hygiene

def hygiene_check(text: str) -> HygieneResult:
    """HARD DROP only for high-certainty invalid content. Everything else passes
    to the LLM (the AI is the primary semantic judge)."""
    if text is None:
        return HygieneResult(passed=False, reason="empty_text")
    stripped = text.strip()
    if not stripped:
        return HygieneResult(passed=False, reason="empty_text")
    if len(stripped) > MAX_TEXT_LENGTH:
        return HygieneResult(passed=False, reason="oversized_text")
    # pure control/noise (e.g. system fragments) — conservative: only when no
    # printable text remains at all
    if not re.search(r"[一-鿿぀-ヿ가-힯a-zA-Z0-9]", stripped):
        return HygieneResult(passed=False, reason="no_text_content")
    return HygieneResult(passed=True)


# ------------------------------------------------------------------ Signals (hints only)

W_DEADLINE = 3.0
W_TIME = 3.0
W_ACTION = 2.0
W_AFFAIR = 1.5
W_AUTHORITY = 2.5

DEADLINE_WORDS = ("截止", "前交", "交到", "提交截止", "ddl", "deadline", "截至", "过期", "限期")
ACTION_WORDS = ("交", "提交", "上传", "发送", "发到", "填写", "报名", "参加", "完成", "预习", "复习", "打印", "准备", "做")
AFFAIR_WORDS = (
    "作业", "习题", "实验报告", "报告", "论文", "试卷", "考试", "测验", "比赛", "竞赛",
    "报名", "活动", "通知", "截止", "测试", "考核", "课堂展示", "ppt", "PPT",
)
AUTHORITY_WORDS = ("老师", "教授", "班长", "学委", "课代表", "辅导员", "教务处", "通知")

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
_COURSEWORK_RE = re.compile(
    r"(?:第[一二三四五六七八九十百\d]+[章节课讲]|"
    r"(?:p|P|页)\s*\d+|"
    r"习题\s*\d+|"
    r"实验[一二三四五六七八九十\d]+)"
)


def analyze_signals(text: str) -> LocalSignals:
    """Extract hint signals. NEVER a semantic veto — score is for hints/audit."""
    score = 0.0
    tags: list[str] = []
    reasons: list[str] = []

    if deadline := _found(text, DEADLINE_WORDS):
        score += W_DEADLINE
        tags.append("deadline")
        reasons.append(f"deadline:{','.join(deadline[:2])}")
    if _TIME_RE.search(text):
        score += W_TIME
        tags.append("time")
        reasons.append("time_expression")
    if actions := _found(text, ACTION_WORDS):
        score += W_ACTION
        tags.append("action")
        reasons.append(f"action:{','.join(actions[:2])}")
    if affairs := _found(text, AFFAIR_WORDS):
        score += W_AFFAIR
        tags.append("affair")
        reasons.append(f"affair:{','.join(affairs[:2])}")
    if authorities := _found(text, AUTHORITY_WORDS):
        score += W_AUTHORITY
        tags.append("authority")
        reasons.append(f"authority:{','.join(authorities[:2])}")
    if _COURSEWORK_RE.search(text):
        score += W_AFFAIR
        tags.append("coursework")
        reasons.append("coursework_reference")

    return LocalSignals(score=round(score, 2), tags=tags, reasons=reasons)


def _found(text: str, words: tuple[str, ...]) -> list[str]:
    return [w for w in words if w in text]
