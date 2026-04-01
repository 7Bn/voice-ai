"""
PracticeConfig — per-practice configuration stored as JSONB on the practices table.

This is what you set up for each customer during the $7,900 onboarding.
Changing any field takes effect on the next call — no code deploy needed.

Fields:
  agent_name          — what the agent calls itself ("Hi, I'm Aria...")
  services            — list of services offered, used to anchor the LLM
  business_hours      — dict of day → [open, close] in HH:MM 24h, or null if closed
  after_hours_message — what to say if called outside business hours (empty = always answer)
  custom_instructions — free-text additions injected at the end of the system prompt
                        (e.g. "Always mention our in-house membership plan for uninsured patients")
  ehr_adapter         — which EHR integration to use: "notify" | "dentrix" | "opendental"
                        "notify" = SMS + email to staff, no API call (v0.1 default)
  tts_voice_id        — TTS voice identifier (ElevenLabs voice_id or Cartesia voice slug)
  llm_model           — LLM model to use (default: claude-sonnet-4-6)
  sms_enabled         — whether to include SMS opt-in in the HIPAA disclosure
"""

from datetime import datetime

from pydantic import BaseModel, Field


class BusinessHours(BaseModel):
    """
    Keyed by lowercase day name.
    Value is [open_time, close_time] in HH:MM 24h format, or null if closed that day.

    Example: {"monday": ["09:00", "17:00"], "saturday": ["09:00", "13:00"], "sunday": null}
    """

    monday: list[str] | None = ["09:00", "17:00"]
    tuesday: list[str] | None = ["09:00", "17:00"]
    wednesday: list[str] | None = ["09:00", "17:00"]
    thursday: list[str] | None = ["09:00", "17:00"]
    friday: list[str] | None = ["09:00", "17:00"]
    saturday: list[str] | None = None
    sunday: list[str] | None = None

    def is_open_now(self, timezone: str) -> bool:
        """Return True if current local time is within business hours."""
        import zoneinfo

        try:
            tz = zoneinfo.ZoneInfo(timezone)
            now = datetime.now(tz)
        except Exception:
            return True  # unknown timezone — don't block calls

        day = now.strftime("%A").lower()
        hours = getattr(self, day, None)
        if hours is None:
            return False

        open_h, open_m = (int(x) for x in hours[0].split(":"))
        close_h, close_m = (int(x) for x in hours[1].split(":"))
        open_minutes = open_h * 60 + open_m
        close_minutes = close_h * 60 + close_m
        current_minutes = now.hour * 60 + now.minute

        return open_minutes <= current_minutes < close_minutes


# Default dental services — used in the system prompt so the LLM knows what to offer
_DEFAULT_SERVICES = [
    "cleaning and hygiene",
    "checkup and exam",
    "filling",
    "crown",
    "extraction",
    "root canal",
    "teeth whitening",
    "Invisalign consultation",
    "dental emergency",
]


class PracticeConfig(BaseModel):
    """
    All per-practice configuration. Serialized as JSONB on the practices table.
    Defaults work for a standard US dental practice with no special requirements.
    """

    agent_name: str = "Aria"
    services: list[str] = Field(default_factory=lambda: list(_DEFAULT_SERVICES))
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    after_hours_message: str = (
        "Our office is currently closed. Please call back during business hours, "
        "or stay on the line and I can capture a message for our team."
    )
    custom_instructions: str = ""
    ehr_adapter: str = "notify"  # "notify" | "dentrix" | "opendental" | "eaglesoft" | "curve"
    tts_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs Rachel — warm, professional
    llm_model: str = "claude-sonnet-4-6"
    sms_enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict | None) -> "PracticeConfig":
        """Load from the JSONB column value. Returns defaults if data is None or empty."""
        if not data:
            return cls()
        return cls.model_validate(data)

    def services_text(self) -> str:
        """Formatted services list for injection into the system prompt."""
        return ", ".join(self.services)
