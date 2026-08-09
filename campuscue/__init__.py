"""CampusAgent — proactive campus affairs agent layer.

This package holds all CampusAgent-specific code. It sits on top of the AstrBot
runtime and deliberately keeps its own boundary: the ``astrbot`` package is
treated as an upstream dependency and is modified in as few places as possible,
so this fork stays rebaseable and the original work is easy to identify.

Layout:
    models      SQLModel tables (campus_tasks, campus_extractions, ...)
    extractor   the three-tier message -> task pipeline (L1/L2/L3)
    tools       FunctionTool implementations exposed to the agent
    api         FastAPI routes serving the task board
    web         Vue single-page task board
"""

__version__ = "0.1.0"
