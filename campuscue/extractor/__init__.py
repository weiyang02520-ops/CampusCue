"""The three-tier message -> task pipeline.

    L1  prefilter    zero tokens, drops chatter on rules alone
    L2  extract      one LLM call, returns structured JSON
    L3  resolve      code turns "周五晚上12点前" into an absolute instant,
                     dedups, and gates on confidence

The split exists for two reasons. Cost: a busy group produces hundreds of
messages a day and sending each to a model is both slow and expensive, so L1
pays nothing to reject the obvious. Accuracy: relative Chinese time expressions
are the single most error-prone part of the job, and a model that computes dates
in its head gets them wrong in ways nobody can audit -- so L2 is instructed to
copy the phrase verbatim and L3 does the arithmetic in code, against the
message's own timestamp.
"""
