"""Replay canned group messages through the real pipeline.

Two jobs, and the second is why this is a shipped module rather than a test
fixture:

1. Development: exercise L1 -> L2 -> L3 -> database end to end without waiting
   for someone to type in a QQ group.
2. The demo. A five-minute pitch that depends on a human posting a message in a
   live group, over conference wifi, through a third-party QQ bridge, has several
   single points of failure and no way to retry. Replay drives the *same*
   pipeline with the same code path, so what the judges watch is the real system
   -- only the transport is swapped.

Usage:
    .venv/Scripts/python.exe -m campuscue.replay --list
    .venv/Scripts/python.exe -m campuscue.replay --scenario homework
    .venv/Scripts/python.exe -m campuscue.replay --all
    .venv/Scripts/python.exe -m campuscue.replay --all --dry-run   # no writes
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from campuscue.extractor.pipeline import MessageContext, process_message, utcnow
from campuscue.extractor.prefilter import prefilter
from campuscue.extractor.timeresolve import CAMPUS_TZ
from campuscue.models import as_utc

DEMO_UMO = "aiocqhttp:GroupMessage:demo-7788"
"""A stable fake origin so replayed tasks group together and can be cleared
between rehearsals without touching real data."""


def quiet_http_logs() -> None:
    """Silence httpx/httpcore wire traces.

    Must run *after* astrbot is imported: ``LogManager`` sets the root logger to
    DEBUG on import (astrbot/core/log.py), so anything configured earlier gets
    overridden. Without this the replay output is buried under per-request wire
    traces -- fine in a terminal, unreadable on a projector.
    """
    for name in ("httpx", "httpcore", "httpcore.http11", "httpcore.connection"):
        logging.getLogger(name).setLevel(logging.WARNING)
    # The pipeline's own INFO lines duplicate what this script prints in a nicer
    # form. Warnings and errors stay visible -- a silent failure on stage is worse
    # than an ugly one.
    logging.getLogger("astrbot").setLevel(logging.WARNING)


@dataclass
class Sample:
    """One canned message, with the sender context a real event would carry."""

    key: str
    label: str
    text: str
    sender_name: str = "张老师"
    group_name: str = "软件工程课程群"
    is_authority: bool = True
    offset_minutes: int = 0
    """Sent this many minutes before now, so a scenario can stage a sequence."""


SAMPLES: tuple[Sample, ...] = (
    Sample(
        "homework",
        "作业通知",
        "实验三报告周五晚上12点前提交，交到学习通，注意查重率不要超过20%",
    ),
    Sample(
        "exam",
        "考试通知",
        "通知：高数考试，下周二8:30，3教405，带身份证和校园卡，不要带计算器",
    ),
    Sample(
        "competition",
        "比赛通知",
        "第八届大学生创新创业大赛开始报名了，截止8月10日，需要提交商业计划书和团队报名表，"
        "有意向的同学找我领取模板",
    ),
    Sample(
        "activity",
        "活动通知",
        "@全体成员 明天下午3点在学术报告厅有企业宣讲会，建议大三大四同学参加，带简历",
        offset_minutes=5,
    ),
    Sample(
        "vague",
        "含糊通知（应进待确认）",
        "那个材料的事情大家记得处理一下，别拖太久",
        offset_minutes=10,
    ),
    Sample(
        "chatter_thanks",
        "闲聊：感谢",
        "谢谢老师！",
        sender_name="李同学",
        is_authority=False,
    ),
    Sample(
        "chatter_laugh",
        "闲聊：表情",
        "哈哈哈哈哈",
        sender_name="王同学",
        is_authority=False,
    ),
    Sample(
        "chatter_lunch",
        "闲聊：约饭（含时间词，L1 放过、L2 应判非任务）",
        "周五一起去吃火锅吗",
        sender_name="王同学",
        is_authority=False,
    ),
    Sample(
        "peer_talk",
        "同学间对话（不是通知）",
        "我上周就交了，你还没交吗",
        sender_name="李同学",
        is_authority=False,
    ),
    Sample(
        "no_keyword",
        "无关键词的真作业",
        "报告周五交",
    ),
)

SAMPLES_BY_KEY = {s.key: s for s in SAMPLES}


def _fmt_deadline(value: datetime | None) -> str:
    # as_utc, not astimezone: values read back from SQLite are naive and would
    # otherwise be misread as local time, shifting every deadline by 8 hours.
    value = as_utc(value)
    if value is None:
        return "—"
    local = value.astimezone(CAMPUS_TZ)
    delta = local - datetime.now(CAMPUS_TZ)
    days = delta.days
    if days < 0:
        when = "已过期"
    elif days == 0:
        when = f"{int(delta.total_seconds() // 3600)}小时后"
    else:
        when = f"{days}天后"
    return f"{local:%m-%d %H:%M} ({when})"


async def replay_one(
    sample: Sample, *, client: httpx.AsyncClient, dry_run: bool = False
) -> None:
    """Push one sample through the pipeline and print what came out."""
    sent_at = utcnow() - timedelta(minutes=sample.offset_minutes)

    print(f"\n\033[1m[{sample.label}]\033[0m {sample.text}")

    if dry_run:
        # L1 alone: proves the free filter's behaviour without an API call or a
        # database write. Useful when rehearsing on a bad connection.
        result = prefilter(sample.text, is_authority_sender=sample.is_authority)
        verdict = "通过" if result.passed else f"拦截({result.reject_reason})"
        print(f"  L1 {verdict}  score={result.score:.1f}")
        for name, hit in result.hits.items():
            print(f"     {name}: {hit}")
        return

    ctx = MessageContext(
        umo=DEMO_UMO,
        text=sample.text,
        sent_at=sent_at,
        message_id=f"replay-{sample.key}-{int(sent_at.timestamp())}",
        sender_id="teacher-001" if sample.is_authority else "student-002",
        sender_name=sample.sender_name,
        # The demo source row has no authority_senders configured, so without
        # this explicit flag a staged teacher message would be scored like any
        # classmate's and terse notices ("报告周五交") would fail L1.
        is_authority=sample.is_authority,
        group_name=sample.group_name,
        source_kind="replay",
    )
    outcome = await process_message(ctx, client=client)

    if outcome.outcome == "l1_rejected":
        print(f"  \033[90mL1 拦截\033[0m ({outcome.detail}) — 未调用模型，0 token")
        return
    if outcome.outcome == "model_said_none":
        ext = outcome.extraction
        print(f"  \033[90m判定非任务\033[0m conf={ext.confidence if ext else '?'}")
        if ext and ext.reason:
            print(f"     理由：{ext.reason}")
        return
    if outcome.outcome == "duplicate":
        print(
            f"  \033[33m重复\033[0m 已存在任务 {outcome.task.title if outcome.task else ''}"
        )
        return
    if outcome.outcome in ("llm_error", "pipeline_error"):
        print(f"  \033[31m失败\033[0m {outcome.detail}")
        return

    task = outcome.task
    assert task is not None
    flag = "待确认" if task.status == "pending_confirm" else "已建任务"
    colour = "33" if task.status == "pending_confirm" else "32"
    print(f"  \033[{colour}m{flag}\033[0m {task.title}")
    print(f"     截止：{_fmt_deadline(task.deadline)}", end="")
    if task.deadline and not task.deadline_is_explicit:
        print("  (时间为推断)", end="")
    print()
    if task.location:
        print(f"     地点：{task.location}")
    if task.items:
        print(f"     携带：{'、'.join(task.items)}")
    print(f"     置信度：{task.confidence:.2f}   来源：{task.source_group_name}")
    if task.extract_reason:
        print(f"     判断依据：{task.extract_reason}")


async def main_async(args: argparse.Namespace) -> int:
    quiet_http_logs()

    if args.list:
        print("可用场景：")
        for sample in SAMPLES:
            print(f"  {sample.key:18} {sample.label}")
        return 0

    if args.all:
        chosen = list(SAMPLES)
    elif args.scenario:
        chosen = []
        for key in args.scenario:
            if key not in SAMPLES_BY_KEY:
                print(f"未知场景：{key}。用 --list 查看可用场景。")
                return 2
            chosen.append(SAMPLES_BY_KEY[key])
    else:
        # The three scenarios the pitch is built around.
        chosen = [SAMPLES_BY_KEY[k] for k in ("homework", "exam", "competition")]

    async with httpx.AsyncClient() as client:
        for sample in chosen:
            await replay_one(sample, client=client, dry_run=args.dry_run)
            if args.pause and sample is not chosen[-1]:
                await asyncio.sleep(args.pause)

    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="campuscue.replay",
        description="把预置群消息灌入真实抽取管道",
    )
    parser.add_argument("--scenario", "-s", action="append", help="场景 key，可重复")
    parser.add_argument("--all", "-a", action="store_true", help="跑全部场景")
    parser.add_argument("--list", "-l", action="store_true", help="列出场景")
    parser.add_argument(
        "--dry-run", action="store_true", help="只跑 L1，不调模型、不写库"
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="场景之间停顿，路演时让评委看清每一条",
    )
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
