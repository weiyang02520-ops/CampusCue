"""L1: decide whether a message is worth an LLM call, using rules only.

Design notes
------------
The probe run (campuscue/_ark_probe.py) showed the model itself is accurate, so
L1's job is not accuracy -- it is throughput. Every message L1 rejects costs
zero tokens and zero latency.

That makes the asymmetry of errors very lopsided:

  * a false negative silently loses a real deadline -- the exact failure the
    product exists to prevent
  * a false positive costs roughly 430 tokens, about a hundredth of a cent

So the threshold is deliberately loose. "报告周五交" carries no deadline keyword
at all yet is real homework, which is why a bare time expression is enough to
pass on its own, and why an authoritative sender gets a large bonus: a teacher
saying almost anything deserves a look, a classmate saying "周五一起吃饭吗" does
not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- keyword groups -------------------------------------------------------
# Weights are tuned so that any single strong signal is enough on its own, and
# two weak signals together also pass. See PASS_THRESHOLD below.

DEADLINE_WORDS = (
    "截止",
    "截至",
    "deadline",
    "ddl",
    "过期",
    "逾期",
    "之前",
    "以前",
    "前交",
    "前提交",
    "前完成",
    "前上交",
    "最后一天",
    "最晚",
    "不得晚于",
    "务必",
)

ACTION_WORDS = (
    "提交",
    "上交",
    "交到",
    "递交",
    "上传",
    "提报",
    "报送",
    "报名",
    "填写",
    "填报",
    "登记",
    "签到",
    "打卡",
    "参加",
    "参与",
    "出席",
    "到场",
    "集合",
    "完成",
    "写完",
    "做完",
    "背诵",
    "默写",
    "听写",
    "抄写",
    "朗读",
    "订正",
    "预习",
    "复习",
    "打印",
    "准备",
    "带上",
    "携带",
    "自备",
    "领取",
    "缴费",
    "交费",
    "补考",
    "重修",
)

AFFAIR_WORDS = (
    "作业",
    "实验",
    "报告",
    "论文",
    "课设",
    "大作业",
    "小组作业",
    "考试",
    "测验",
    "小测",
    "期中",
    "期末",
    "补考",
    "答辩",
    "比赛",
    "竞赛",
    "大赛",
    "选拔",
    "初赛",
    "复赛",
    "决赛",
    "活动",
    "讲座",
    "会议",
    "培训",
    "社团",
    "志愿",
    "通知",
    "公告",
    "要求",
    "材料",
    "表格",
    "附件",
)

NOTICE_MARKERS = ("@全体成员", "【通知】", "【公告】", "各位同学", "同学们", "请各位")

# Chatter that should not pass on its own. Checked as a whole-message match so a
# real notice containing "好的" is unaffected.
PURE_CHATTER = re.compile(
    r"^\W*("
    r"哈+|呵+|嘿+|嘻+"
    r"|[好行嗯哦噢啊呀哇]+的?"
    r"|谢谢?(老师|大佬|了)?|多谢|感谢"
    r"|收到|明白|了解|知道了|懂了|ok|OK|okk*"
    r"|在吗|在么|有人吗"
    r"|早|早上好|中午好|晚上好|晚安|再见|拜拜"
    r"|加油|牛|强|666+|\?+|？+|!+|！+|\.+|。+"
    r")\W*$",
    re.IGNORECASE,
)

# --- time expressions -----------------------------------------------------
# Only patterns that could plausibly anchor a deadline. Written to match the way
# notices are actually phrased in Chinese group chats, not to be exhaustive
# about Chinese time vocabulary.

TIME_PATTERNS: tuple[tuple[str, str], ...] = (
    # 8月10日 / 8/10 / 2026-08-10 / 8月10号
    #
    # Deliberately loose, including the bare "3-5" hyphen form. L1 is a coarse
    # filter whose worst failure is silently dropping a real task ("习题3-5、
    # 3-7做一下" carries no other signal that it is homework) -- a false pass
    # costs ~430 tokens, a false drop loses a deadline the product exists to
    # catch. Whether "3-5" is actually a date is L3's job (timeresolve), which
    # refuses the bare hyphen form precisely.
    ("date", r"(?:20\d{2}\s*[-/年]\s*)?\d{1,2}\s*[-/月]\s*\d{1,2}\s*[日号]?"),
    # 周五 / 星期二 / 下周三 / 本周日 / 下下周一
    ("weekday", r"(?:这|本|下|下下|上)?\s*(?:周|星期|礼拜)\s*[一二三四五六天日1-7]"),
    # 今天 / 明天 / 后天 / 大后天 / 明早 / 今晚
    ("dayword", r"今[天日晚早]|明[天日晚早]|后天|大后天|次日|当天"),
    # 12点 / 8:30 / 8：30 / 晚上12点 / 中午12点半 / 23时59分
    (
        "clock",
        r"(?:凌晨|早上|上午|中午|下午|傍晚|晚上|晚|夜里)?\s*"
        r"\d{1,2}\s*(?:[:：]\s*\d{1,2}|[点时](?:\s*\d{1,2}\s*分?|\s*半|\s*整)?)",
    ),
    # 本周内 / 这个月底 / 月末 / 学期末
    ("span", r"(?:本|这)(?:周|星期|月)内?|月底|月末|周末|学期末|假期前"),
    # 三天内 / 24小时内 / 两周后
    (
        "relative",
        r"[0-9一二三四五六七八九十两]+\s*(?:天|日|周|星期|小时|个?月)\s*(?:内|后|之内|以内)",
    ),
)

_COMPILED_TIME = tuple((name, re.compile(pat)) for name, pat in TIME_PATTERNS)

# --- coursework references -------------------------------------------------
# Teachers often skip the word "作业" entirely: "完成第35页到第40页" or "习题
# 3-5、3-7 做一下". None of the keyword groups above fire on those, and page
# numbers match no time pattern, so without this group the message scores only
# W_ACTION = 2.0 and never reaches the model. Deliberately not strong enough to
# pass on its own -- "答案在第35页" should stay out.

COURSEWORK_PATTERNS: tuple[tuple[str, str], ...] = (
    # 第35页 / 35-40页 / P35 / p35-40 / 第三十五页
    (
        "page",
        r"(?:第\s*)?(?:[0-9]+|[一二三四五六七八九十百]+)\s*(?:[-~到至]\s*(?:[0-9]+|[一二三四五六七八九十百]+)\s*)?页"
        r"|(?<![A-Za-z0-9])[Pp]\.?\s?\d{1,3}(?:\s*[-~至到]\s*\d{1,3})?(?![0-9])",
    ),
    # 习题3-5 / 练习题2、4 / 第5题 / 课后题 / 第3、5、7小题
    (
        "exercise",
        r"(?:习题|练习题|课后题|课后练习|作业题|例题)\s*[0-9一二三四五六七八九十.\-、,，~至到]*|第\s*[0-9一二三四五六七八九十]+\s*[、,，]?\s*[0-9一二三四五六七八九十、,，]*\s*(?:小?题)",
    ),
    # 第三章 / 第5单元 / 实验二 / Chapter 3
    (
        "chapter",
        r"第\s*[0-9一二三四五六七八九十]+\s*(?:章|节|单元|课|讲)|[Cc]hapter\s*\d+",
    ),
    # 课本/教材/练习册/试卷/学案
    ("material", r"课本|教材|书上|书本|练习册|习题册|试卷|学案|讲义|工作纸|作业本"),
)

_COMPILED_COURSEWORK = tuple(
    (name, re.compile(pat)) for name, pat in COURSEWORK_PATTERNS
)

# --- scoring --------------------------------------------------------------

W_DEADLINE = 3.0
W_TIME = 3.0
W_ACTION = 2.0
W_AFFAIR = 1.5
W_COURSEWORK = 1.5
W_NOTICE_MARKER = 2.0
W_AUTHORITY = 2.5
W_URL = 0.5

PASS_THRESHOLD = 3.0
"""Any one of: a deadline word, a time expression, a teacher-plus-affair
combination, or an action-plus-affair combination. A lone affair word ("这次
作业好难") scores 1.5 and is correctly rejected."""

MIN_LENGTH = 4
MAX_LENGTH = 2000


@dataclass
class PrefilterResult:
    """Why L1 decided what it decided. Stored on the extraction row and shown
    as the first step of the trace panel in the UI."""

    passed: bool
    score: float
    hits: dict[str, list[str] | str | bool] = field(default_factory=dict)
    reject_reason: str | None = None

    def as_hits_json(self) -> dict:
        return {"score": round(self.score, 2), **self.hits}


def _found(text: str, words: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [w for w in words if w.lower() in lowered]


def prefilter(
    text: str,
    *,
    is_authority_sender: bool = False,
) -> PrefilterResult:
    """Score one message and decide whether it goes on to the LLM.

    Args:
        text: The message body.
        is_authority_sender: True when the sender is a teacher, monitor or group
            admin -- recorded per group in ``CampusSource.authority_senders``.

    Returns:
        A PrefilterResult carrying the decision, the score, and which rules fired.
    """
    stripped = text.strip()

    if len(stripped) < MIN_LENGTH:
        return PrefilterResult(False, 0.0, reject_reason="too_short")
    if len(stripped) > MAX_LENGTH:
        # Pasted articles and forwarded chat logs. Handling these well needs
        # chunking, which is not in the MVP.
        return PrefilterResult(False, 0.0, reject_reason="too_long")
    if PURE_CHATTER.match(stripped):
        return PrefilterResult(False, 0.0, reject_reason="pure_chatter")

    hits: dict[str, list[str] | str | bool] = {}
    score = 0.0

    if deadline := _found(stripped, DEADLINE_WORDS):
        score += W_DEADLINE
        hits["deadline_words"] = deadline

    times: list[str] = []
    for name, pattern in _COMPILED_TIME:
        for match in pattern.finditer(stripped):
            times.append(f"{name}:{match.group().strip()}")
    if times:
        score += W_TIME
        hits["time_expressions"] = times

    if action := _found(stripped, ACTION_WORDS):
        score += W_ACTION
        hits["action_words"] = action

    if affair := _found(stripped, AFFAIR_WORDS):
        score += W_AFFAIR
        hits["affair_words"] = affair

    coursework: list[str] = []
    for name, pattern in _COMPILED_COURSEWORK:
        match = pattern.search(stripped)
        if match:
            coursework.append(f"{name}:{match.group().strip()}")
    if coursework:
        score += W_COURSEWORK
        hits["coursework_refs"] = coursework

    if marker := _found(stripped, NOTICE_MARKERS):
        score += W_NOTICE_MARKER
        hits["notice_markers"] = marker

    if is_authority_sender:
        score += W_AUTHORITY
        hits["authority_sender"] = True

    if "http://" in stripped or "https://" in stripped:
        score += W_URL
        hits["has_url"] = True

    passed = score >= PASS_THRESHOLD
    return PrefilterResult(
        passed=passed,
        score=score,
        hits=hits,
        reject_reason=None if passed else "below_threshold",
    )


__all__ = ["PASS_THRESHOLD", "PrefilterResult", "prefilter"]
