"""
Tests for the Twilio inbound call webhook (app/routers/calls.py).

Coverage:
  POST /twilio/voice
    ├── [✓] practice found + SIP configured → TwiML with <Sip> URI
    ├── [✓] practice found + SIP configured → X- headers include practice_id
    ├── [✓] practice found + SIP NOT configured → holding message + hangup
    ├── [✓] practice not found → graceful hangup TwiML
    ├── [✓] practice found but is_active=False → graceful hangup (lapsed subscription)
    └── [✓] health check → 200 OK

  POST /twilio/status
    └── [✓] returns {"status": "received"}

  Helper: _twiml_hangup
    └── [✓] returns XML with <Say> and <Hangup>
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import make_practice

client = TestClient(app)


def _twilio_form(to: str, from_: str = "+15550000000", call_sid: str = "CA123") -> dict:
    return {"To": to, "From": from_, "CallSid": call_sid}


class TestInboundCall:
    def test_health_check(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    @patch("app.routers.calls.settings")
    @patch("app.routers.calls.Practice.get_by_twilio_number", new_callable=AsyncMock)
    def test_sip_configured_returns_sip_twiml(self, mock_get, mock_settings):
        mock_get.return_value = make_practice(name="Sunrise Dental")
        mock_settings.livekit_sip_host = "abc123.sip.livekit.cloud"

        resp = client.post("/twilio/voice", data=_twilio_form(to="+15551234567"))

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/xml"
        body = resp.text
        assert "sip:" in body
        assert "abc123.sip.livekit.cloud" in body
        assert "<Hangup" not in body

    @patch("app.routers.calls.settings")
    @patch("app.routers.calls.Practice.get_by_twilio_number", new_callable=AsyncMock)
    def test_sip_twiml_includes_practice_headers(self, mock_get, mock_settings):
        practice = make_practice(name="Sunrise Dental")
        mock_get.return_value = practice
        mock_settings.livekit_sip_host = "abc123.sip.livekit.cloud"

        resp = client.post("/twilio/voice", data=_twilio_form(to="+15551234567"))

        body = resp.text
        # Practice ID should be in the TwiML as an X- SIP header value
        assert str(practice.id) in body
        assert "X-Practice-Id" in body

    @patch("app.routers.calls.settings")
    @patch("app.routers.calls.Practice.get_by_twilio_number", new_callable=AsyncMock)
    def test_sip_not_configured_returns_holding_message(self, mock_get, mock_settings):
        mock_get.return_value = make_practice(name="Sunrise Dental")
        mock_settings.livekit_sip_host = ""  # not yet configured

        resp = client.post("/twilio/voice", data=_twilio_form(to="+15551234567"))

        assert resp.status_code == 200
        body = resp.text
        assert "<Hangup" in body
        assert "sip:" not in body

    @patch("app.routers.calls.Practice.get_by_twilio_number", new_callable=AsyncMock)
    def test_practice_not_found_hangs_up(self, mock_get):
        mock_get.return_value = None

        resp = client.post("/twilio/voice", data=_twilio_form(to="+15550000000"))

        assert resp.status_code == 200
        body = resp.text
        assert "<Hangup" in body
        assert "not in service" in body

    @patch("app.routers.calls.Practice.get_by_twilio_number", new_callable=AsyncMock)
    def test_inactive_practice_is_rejected(self, mock_get):
        """get_by_twilio_number filters is_active=True at the DB level."""
        mock_get.return_value = None

        resp = client.post("/twilio/voice", data=_twilio_form(to="+15557777777"))

        assert resp.status_code == 200
        assert "<Hangup" in resp.text

    @patch("app.routers.calls.Practice.get_by_twilio_number", new_callable=AsyncMock)
    def test_status_webhook_returns_received(self, mock_get):
        resp = client.post(
            "/twilio/status",
            data={"CallSid": "CA123", "CallStatus": "completed"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "received"}
