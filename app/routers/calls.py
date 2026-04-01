"""
Twilio inbound call webhook — entry point for every patient call.

Flow:
  POST /twilio/voice (Twilio sends this when a call comes in)
    ├── Look up practice by the Twilio number dialed (To field)
    ├── If not found → hang up gracefully
    ├── If subscription lapsed (is_active=False) → hang up
    └── Return TwiML <Dial><Sip> to connect the call to LiveKit

TwiML → LiveKit SIP flow:
  1. Twilio calls POST /twilio/voice
  2. We return <Dial><Sip sip:{To}@{LIVEKIT_SIP_HOST}> with X- headers carrying
     practice metadata (practice_id, config, etc.)
  3. LiveKit's SIP trunk receives the INVITE, maps X- headers to attributes
     via the dispatch rule's headers_to_attributes config (set up by livekit_setup.py)
  4. LiveKit creates a room, dispatches the agent worker job
  5. Agent reads ctx.job.metadata (JSON) — all the X- header values are there

Run `python -m app.livekit_setup setup` once per deployment to create the
SIP trunk and dispatch rule. Then set LIVEKIT_SIP_HOST in .env.
"""

import json
import urllib.parse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.twiml.voice_response import VoiceResponse

from app.config import settings
from app.database import get_db
from app.models.practice import Practice

router = APIRouter(prefix="/twilio", tags=["calls"])


def _twiml_hangup(message: str) -> Response:
    vr = VoiceResponse()
    vr.say(message)
    vr.hangup()
    return Response(content=str(vr), media_type="application/xml")


@router.post("/voice")
async def inbound_call(
    request: Request,
    To: str = Form(...),
    From: str = Form(...),
    CallSid: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Twilio calls this webhook when a patient dials the practice number.
    We look up the practice, then connect the call to LiveKit via SIP.
    """
    practice = await Practice.get_by_twilio_number(db, twilio_number=To)

    if practice is None:
        return _twiml_hangup("This number is not in service. Goodbye.")

    config = practice.get_config()

    # Build the SIP URI. LiveKit's SIP host comes from LIVEKIT_SIP_HOST env var,
    # set after running `python -m app.livekit_setup setup`.
    # The "To" number becomes the SIP username — LiveKit uses it to match
    # the dispatch rule and route the call to the right agent job.
    sip_host = settings.livekit_sip_host
    if not sip_host:
        # SIP not configured — fall back to a holding message.
        # This should only happen before livekit_setup.py has been run.
        vr = VoiceResponse()
        vr.say(
            f"Thank you for calling {practice.name}. "
            "Our system is being set up. Please try again shortly."
        )
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    # Strip non-digit chars from the called number for the SIP username
    sip_user = "".join(c for c in To if c.isdigit() or c == "+")
    sip_uri = f"sip:{sip_user}@{sip_host}"

    # Pass practice context as SIP URI header parameters (RFC 3261 §19.1.1).
    # Format: sip:user@host?Header-Name=value&Header-Name-2=value2
    # LiveKit's SIP trunk maps these to dispatch rule attributes via
    # headers_to_attributes (configured in livekit_setup.py).
    # The agent reads them from ctx.job.attributes.
    #
    # Note: X-Practice-Config (the full PracticeConfig JSON) is URL-encoded
    # because it may contain characters invalid in SIP URIs.
    sip_headers = {
        "X-Practice-Id":       str(practice.id),
        "X-Practice-Name":     practice.name,
        "X-Practice-State":    practice.state,
        "X-Practice-Timezone": practice.timezone,
        "X-Escalation-Number": practice.escalation_number,
        "X-Staff-Email":       practice.staff_email or "",
        "X-Call-Sid":          CallSid,
        "X-Patient-Phone":     From,
        "X-Stt-Provider":      practice.stt_provider,
        "X-Tts-Provider":      practice.tts_provider,
        "X-Ehr-Adapter":       config.ehr_adapter,
        "X-Practice-Config":   json.dumps(config.model_dump()),
    }

    # Encode headers into the SIP URI query string
    sip_uri_with_headers = f"{sip_uri}?{urllib.parse.urlencode(sip_headers)}"

    vr = VoiceResponse()
    dial = vr.dial(answer_on_bridge=True, action="/twilio/status")
    dial.sip(sip_uri_with_headers)

    return Response(content=str(vr), media_type="application/xml")


@router.post("/status")
async def call_status(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Twilio calls this when a call ends or changes status.
    Logs the event — the agent handles final DB writes via /internal/finalize_call.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Call status update: {CallSid} → {CallStatus}")
    return {"status": "received"}
