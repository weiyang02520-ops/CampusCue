"""SettingsService (M5) — persisted settings via schema v3 ``settings`` table.

First-version settings are intentionally small: timezone, theme,
message_retention_days, and M3 reminder defaults that are meaningful today.
Values that cannot be applied to a running process are reported with
``restart_required`` by the API layer.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from campuscue.repositories.repositories import SettingRepository
from campuscue.storage.models import Setting

DEFAULT_SETTINGS: dict[str, object] = {
    "timezone": "Asia/Shanghai",
    "theme": "system",
    "message_retention_days": 30,
    "reminder_default_enabled": True,
    "reminder_min_lead_seconds": 60,
    "reminder_quiet_start_hour": 23,
    "reminder_quiet_end_hour": 8,
}

_ALLOWED_THEMES = {"system", "light", "dark"}
_RESTART_REQUIRED_KEYS = {"timezone"}


class SettingsService:
    def __init__(self, settings: SettingRepository, *, default_timezone: str = "Asia/Shanghai") -> None:
        self._settings = settings
        self._default_timezone = default_timezone

    async def get_all(self) -> dict[str, object]:
        result = dict(DEFAULT_SETTINGS)
        result["timezone"] = self._default_timezone
        rows = await self._settings.list_all()
        for row in rows:
            value = row.value
            if row.key in result and isinstance(value, type(result[row.key])):
                result[row.key] = value
            elif row.key not in result:
                # tolerate unknown stored keys but do not expose them as contract
                pass
        return result

    async def patch(self, updates: dict[str, object]) -> dict[str, object]:
        validated = self._validate(updates)
        for key, value in validated.items():
            await self._settings.set(key, value)
        return await self.get_all()

    @staticmethod
    def _validate(updates: dict[str, object]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in updates.items():
            if key == "timezone":
                if not isinstance(value, str) or not value:
                    raise ValueError("timezone must be a non-empty string")
                try:
                    ZoneInfo(value)
                except Exception as e:
                    raise ValueError(f"invalid timezone {value!r}: {e}") from None
                out[key] = value
            elif key == "theme":
                if value not in _ALLOWED_THEMES:
                    raise ValueError(f"invalid theme {value!r}")
                out[key] = value
            elif key == "message_retention_days":
                if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 3650:
                    raise ValueError("message_retention_days must be an int in [1, 3650]")
                out[key] = value
            elif key == "reminder_default_enabled":
                if not isinstance(value, bool):
                    raise ValueError("reminder_default_enabled must be a bool")
                out[key] = value
            elif key == "reminder_min_lead_seconds":
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                    raise ValueError("reminder_min_lead_seconds must be > 0")
                out[key] = int(value)
            elif key == "reminder_quiet_start_hour":
                if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < 24:
                    raise ValueError("reminder_quiet_start_hour must be an int in [0, 23]")
                out[key] = value
            elif key == "reminder_quiet_end_hour":
                if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < 24:
                    raise ValueError("reminder_quiet_end_hour must be an int in [0, 23]")
                out[key] = value
            else:
                raise ValueError(f"unknown setting key: {key!r}")
        return out

    @staticmethod
    def restart_required_keys(updates: dict[str, object]) -> list[str]:
        return [k for k in updates if k in _RESTART_REQUIRED_KEYS]
