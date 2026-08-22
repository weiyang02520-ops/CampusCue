# Demo Troubleshooting

## API is unavailable

Confirm the backend process is running, the API is loopback-bound, and the
WebUI is using the same local API token. Do not disable auth or bind the demo
to `0.0.0.0` as a workaround.

## No Agent answer

Confirm an enabled Provider exists and that `CAMPUSCUE_AGENT=1` and
`CAMPUSCUE_TASK_PIPELINE=1` are set. The deterministic acceptance harness
does not require a real Provider.

## Reminder did not reach QQ

The default is intentionally `CAMPUSCUE_REMINDER_DELIVERY=noop`; a scheduled
or fired reminder is not proof of QQ delivery. For a controlled OneBot test,
use only a dedicated account and group, set `CAMPUSCUE_REMINDER_DELIVERY=onebot`,
and never put its token or IDs in documentation/evidence.

## Acceptance test leaves state behind

The M7-A10 test uses an isolated temporary database. Re-run the test rather
than deleting production SQLite rows by hand.
