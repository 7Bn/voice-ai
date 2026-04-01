"""
Tests for PracticeConfig (app/models/practice_config.py) and
the updated build_system_prompt (app/agent/prompts.py).

Coverage:
  PracticeConfig
    ├── [✓] defaults work for a standard dental practice
    ├── [✓] from_dict() with None returns defaults
    ├── [✓] from_dict() with partial dict merges with defaults
    ├── [✓] from_dict() with full dict round-trips correctly
    ├── [✓] services_text() joins service list
    └── [✓] custom agent_name is preserved

  BusinessHours
    ├── [✓] is_open_now() returns True during business hours (mocked)
    ├── [✓] is_open_now() returns False outside business hours (mocked)
    ├── [✓] is_open_now() returns False on a closed day (e.g. Sunday)
    └── [✓] is_open_now() returns True for unknown timezone (fail-open)

  build_system_prompt
    ├── [✓] includes practice name
    ├── [✓] includes agent name from config
    ├── [✓] includes services list
    ├── [✓] includes custom_instructions when set
    ├── [✓] omits custom_instructions block when empty
    └── [✓] works with default config (no config passed)
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.agent.prompts import build_system_prompt
from app.agent.state import ConversationState
from app.models.practice_config import BusinessHours, PracticeConfig


class TestPracticeConfig:
    def test_defaults_are_valid(self):
        cfg = PracticeConfig()
        assert cfg.agent_name == "Aria"
        assert len(cfg.services) > 0
        assert cfg.ehr_adapter == "notify"
        assert cfg.sms_enabled is True

    def test_from_dict_none_returns_defaults(self):
        cfg = PracticeConfig.from_dict(None)
        assert cfg.agent_name == "Aria"

    def test_from_dict_empty_dict_returns_defaults(self):
        cfg = PracticeConfig.from_dict({})
        assert cfg.agent_name == "Aria"

    def test_from_dict_partial_dict_overrides_fields(self):
        cfg = PracticeConfig.from_dict({"agent_name": "Sophie", "ehr_adapter": "dentrix"})
        assert cfg.agent_name == "Sophie"
        assert cfg.ehr_adapter == "dentrix"
        # Other defaults intact
        assert cfg.sms_enabled is True

    def test_from_dict_full_round_trip(self):
        original = PracticeConfig(
            agent_name="Max",
            services=["cleaning", "filling"],
            ehr_adapter="opendental",
            custom_instructions="Always mention our membership plan.",
            sms_enabled=False,
        )
        data = original.model_dump()
        restored = PracticeConfig.from_dict(data)
        assert restored.agent_name == "Max"
        assert restored.services == ["cleaning", "filling"]
        assert restored.ehr_adapter == "opendental"
        assert restored.custom_instructions == "Always mention our membership plan."
        assert restored.sms_enabled is False

    def test_services_text_joins_list(self):
        cfg = PracticeConfig(services=["cleaning", "filling", "crown"])
        assert cfg.services_text() == "cleaning, filling, crown"

    def test_custom_agent_name_preserved(self):
        cfg = PracticeConfig(agent_name="Nova")
        assert cfg.agent_name == "Nova"


class TestBusinessHours:
    def _make_hours(self) -> BusinessHours:
        return BusinessHours(
            monday=["09:00", "17:00"],
            tuesday=["09:00", "17:00"],
            wednesday=["09:00", "17:00"],
            thursday=["09:00", "17:00"],
            friday=["09:00", "17:00"],
            saturday=None,
            sunday=None,
        )

    def test_open_during_business_hours(self):
        hours = self._make_hours()
        # Mock datetime to Monday 10:30 AM
        mock_dt = datetime(2026, 3, 30, 10, 30, tzinfo=timezone.utc)  # Monday
        with patch("app.models.practice_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            result = hours.is_open_now("UTC")
        assert result is True

    def test_closed_outside_business_hours(self):
        hours = self._make_hours()
        # Mock datetime to Monday 8:00 AM (before 9am)
        mock_dt = datetime(2026, 3, 30, 8, 0, tzinfo=timezone.utc)  # Monday
        with patch("app.models.practice_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            result = hours.is_open_now("UTC")
        assert result is False

    def test_closed_on_sunday(self):
        hours = self._make_hours()
        # Mock datetime to Sunday 11:00 AM
        mock_dt = datetime(2026, 3, 29, 11, 0, tzinfo=timezone.utc)  # Sunday
        with patch("app.models.practice_config.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            result = hours.is_open_now("UTC")
        assert result is False

    def test_unknown_timezone_fails_open(self):
        hours = self._make_hours()
        # Should not raise, should return True (fail-open = don't block calls)
        result = hours.is_open_now("Not/ATimezone")
        assert result is True


class TestBuildSystemPrompt:
    def test_includes_practice_name(self):
        prompt = build_system_prompt("Sunrise Dental", "NY", ConversationState.GREETING)
        assert "Sunrise Dental" in prompt

    def test_includes_agent_name_from_config(self):
        cfg = PracticeConfig(agent_name="Nova")
        prompt = build_system_prompt("Sunrise Dental", "NY", ConversationState.GREETING, cfg)
        assert "Nova" in prompt

    def test_includes_services_list(self):
        cfg = PracticeConfig(services=["cleaning", "filling", "crown"])
        prompt = build_system_prompt("Sunrise Dental", "NY", ConversationState.GREETING, cfg)
        assert "cleaning" in prompt
        assert "filling" in prompt
        assert "crown" in prompt

    def test_includes_custom_instructions(self):
        cfg = PracticeConfig(custom_instructions="Always mention our membership plan.")
        prompt = build_system_prompt("Sunrise Dental", "NY", ConversationState.GREETING, cfg)
        assert "Always mention our membership plan." in prompt

    def test_omits_custom_instructions_block_when_empty(self):
        cfg = PracticeConfig(custom_instructions="")
        prompt = build_system_prompt("Sunrise Dental", "NY", ConversationState.GREETING, cfg)
        assert "PRACTICE-SPECIFIC INSTRUCTIONS" not in prompt

    def test_works_with_no_config_passed(self):
        prompt = build_system_prompt("Valley Dental", "CA", ConversationState.COLLECT_DETAILS)
        assert "Valley Dental" in prompt
        assert "Aria" in prompt  # default agent name
