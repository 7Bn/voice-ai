"""
LiveKit SIP provisioning — run once per deployment to create the inbound
SIP trunk and dispatch rule that routes Twilio calls to the agent worker.

This is NOT called on every inbound call. It's a one-time setup that creates
the persistent LiveKit objects. Re-run if you need to update the trunk config.

Usage:
  python -m app.livekit_setup              # create trunk + dispatch rule
  python -m app.livekit_setup --dry-run    # show what would be created
  python -m app.livekit_setup --list       # show existing trunks + rules

How it connects to the call flow:
  1. This script creates an inbound SIP trunk in LiveKit.
     LiveKit gives back a SIP hostname: e.g. abc123.sip.livekit.cloud
  2. Store that hostname in settings (LIVEKIT_SIP_HOST).
  3. Twilio calls POST /twilio/voice → we return TwiML with:
       <Dial><Sip>sip:{called_number}@{LIVEKIT_SIP_HOST};...</Sip></Dial>
  4. LiveKit receives the SIP INVITE, checks the dispatch rule, creates a room,
     dispatches the agent worker job with the metadata from the SIP headers.
  5. Agent reads ctx.job.metadata (JSON) to get practice_id, patient_phone, etc.
"""

import asyncio
import json
import logging

import click

from app.config import settings

logger = logging.getLogger(__name__)


async def create_sip_trunk_and_dispatch_rule(dry_run: bool = False, existing_trunk_id: str | None = None) -> dict:
    """
    Create the LiveKit inbound SIP trunk and dispatch rule.

    The trunk accepts calls from any Twilio IP (Twilio's SIP ranges).
    The dispatch rule routes every call to its own room (SIPDispatchRuleIndividual)
    so each patient call gets an isolated LiveKit room.

    Returns a dict with trunk_id, dispatch_rule_id, sip_host.
    """
    from livekit import api
    from livekit.protocol.sip import (
        CreateSIPDispatchRuleRequest,
        CreateSIPInboundTrunkRequest,
        SIPDispatchRule,
        SIPDispatchRuleIndividual,
        SIPDispatchRuleInfo,
        SIPInboundTrunkInfo,
    )

    if not settings.livekit_url or not settings.livekit_api_key:
        raise RuntimeError("LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET must be set")

    click.echo(f"\nLiveKit URL:   {settings.livekit_url}")
    click.echo(f"API key:       {settings.livekit_api_key[:8]}...")

    if dry_run:
        click.echo("\n[DRY RUN] Would create:")
        click.echo("  - SIP inbound trunk (accepts Twilio PSTN calls)")
        click.echo("  - SIP dispatch rule (routes each call to its own room)")
        click.echo("\nHeaders mapped to agent attributes:")
        for header, attr in _HEADER_ATTRIBUTE_MAP.items():
            click.echo(f"  {header} → {attr}")
        return {}

    lkapi = api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )

    try:
        # Step 1: Create inbound SIP trunk (skip if existing_trunk_id provided)
        if existing_trunk_id:
            trunk_id = existing_trunk_id
            click.echo(f"\n[OK] Reusing existing SIP trunk: {trunk_id}")
        else:
            trunk_info = SIPInboundTrunkInfo(
                name="Voice AI Receptionist — Twilio Inbound",
            )

            # Allow calls from any address — Twilio uses a large, changing IP range.
            # In production, scope to Twilio's published SIP IP ranges for defense-in-depth.
            trunk_info.allowed_addresses.append("0.0.0.0/0")

            # Map SIP X- headers (sent by our TwiML) to LiveKit attributes.
            # These become available to the agent as ctx.job.metadata (JSON).
            for header, attribute in _HEADER_ATTRIBUTE_MAP.items():
                trunk_info.headers_to_attributes[header] = attribute

            trunk_req = CreateSIPInboundTrunkRequest(trunk=trunk_info)
            trunk = await lkapi.sip.create_inbound_trunk(trunk_req)
            trunk_id = trunk.sip_trunk_id

            click.echo(f"\n[OK] SIP trunk created: {trunk_id}")

        # Step 2: Create dispatch rule — one room per call
        individual_rule = SIPDispatchRuleIndividual(
            room_prefix="call_",
        )

        dispatch_rule = SIPDispatchRule()
        dispatch_rule.dispatch_rule_individual.CopyFrom(individual_rule)

        rule_info = SIPDispatchRuleInfo(
            name="Voice AI Receptionist — Patient Calls",
            rule=dispatch_rule,
        )
        rule_info.trunk_ids.append(trunk_id)

        # Metadata is a JSON string that agents can read via ctx.job.metadata.
        # We also pass it via SIP X- headers per call (practice-specific fields come
        # from the Twilio webhook TwiML, not this static dispatch rule).
        rule_info.metadata = json.dumps({"service": "voice_ai_receptionist", "version": "1.0"})

        dispatch_req = CreateSIPDispatchRuleRequest()
        dispatch_req.dispatch_rule.CopyFrom(rule_info)

        rule = await lkapi.sip.create_dispatch_rule(dispatch_req)
        rule_id = rule.sip_dispatch_rule_id

        click.echo(f"[OK] Dispatch rule created: {rule_id}")

    finally:
        await lkapi.aclose()

    result = {"trunk_id": trunk_id, "dispatch_rule_id": rule_id}
    click.echo(f"\nNext step: set LIVEKIT_SIP_TRUNK_ID={trunk_id} in your .env")
    click.echo("Then run a test call to verify the SIP connection.")
    return result


async def list_sip_config() -> None:
    """List existing SIP trunks and dispatch rules."""
    from livekit import api
    from livekit.protocol.sip import ListSIPInboundTrunkRequest, ListSIPDispatchRuleRequest

    lkapi = api.LiveKitAPI(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )

    try:
        trunks = await lkapi.sip.list_inbound_trunk(ListSIPInboundTrunkRequest())
        click.echo(f"\nSIP Inbound Trunks ({len(trunks.items)}):")
        for t in trunks.items:
            click.echo(f"  {t.sip_trunk_id}  {t.name}")

        rules = await lkapi.sip.list_dispatch_rule(ListSIPDispatchRuleRequest())
        click.echo(f"\nSIP Dispatch Rules ({len(rules.items)}):")
        for r in rules.items:
            click.echo(f"  {r.sip_dispatch_rule_id}  {r.name}  trunks={list(r.trunk_ids)}")
    finally:
        await lkapi.aclose()


# SIP X- headers sent from Twilio TwiML → LiveKit attribute names.
# These become the JSON keys in the agent's ctx.job.metadata.
_HEADER_ATTRIBUTE_MAP = {
    "X-Practice-Id":       "practice_id",
    "X-Practice-Name":     "practice_name",
    "X-Practice-State":    "practice_state",
    "X-Practice-Timezone": "practice_timezone",
    "X-Escalation-Number": "escalation_number",
    "X-Staff-Email":       "staff_email",
    "X-Call-Sid":          "call_sid",
    "X-Patient-Phone":     "patient_phone",
    "X-Stt-Provider":      "stt_provider",
    "X-Tts-Provider":      "tts_provider",
    "X-Ehr-Adapter":       "ehr_adapter",
    "X-Practice-Config":   "config",  # JSON-encoded PracticeConfig
}


@click.group()
def cli():
    pass


@cli.command("setup")
@click.option("--dry-run", is_flag=True)
@click.option("--trunk-id", default=None, help="Reuse existing trunk ID, skip trunk creation.")
def setup(dry_run, trunk_id):
    """Create LiveKit SIP trunk and dispatch rule."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(create_sip_trunk_and_dispatch_rule(dry_run=dry_run, existing_trunk_id=trunk_id))


@cli.command("list")
def list_config():
    """List existing SIP trunks and dispatch rules."""
    asyncio.run(list_sip_config())


if __name__ == "__main__":
    cli()
