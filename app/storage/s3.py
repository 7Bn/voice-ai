"""
Azure Blob Storage for call transcripts and audio recordings.

All blobs are stored with server-side encryption (SSE) enabled by default
on the Azure Storage account — enable at account level in the portal.
Use a HIPAA-eligible Azure region (e.g. East US, West US 2).
Retention: configure a lifecycle management policy on the container (6 years).

Blob layout (mirrors the original S3 key layout — no other code changes needed):
  practices/{practice_id}/calls/{call_sid}/transcript.txt
  practices/{practice_id}/calls/{call_sid}/recording.mp3  ← uploaded via Twilio callback

HIPAA checklist for this storage account:
  - Sign a BAA with Microsoft (available via Azure portal → Compliance → BAA)
  - Enable encryption at rest (on by default for all Azure storage accounts)
  - Enable soft delete (accidental deletion protection)
  - Set container access to Private (no public access)
  - Use a HIPAA-eligible region

Never store PHI in blob names or metadata — only in the encrypted content body.
"""

import logging
from io import BytesIO

from azure.core.exceptions import AzureError
from azure.storage.blob import BlobServiceClient

from app.config import settings

logger = logging.getLogger(__name__)


def _blob_client(blob_name: str):
    """Return an Azure BlobClient for the given blob name."""
    service = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
    return service.get_blob_client(
        container=settings.azure_storage_container,
        blob=blob_name,
    )


def transcript_key(practice_id: str, call_sid: str) -> str:
    return f"practices/{practice_id}/calls/{call_sid}/transcript.txt"


def recording_key(practice_id: str, call_sid: str) -> str:
    return f"practices/{practice_id}/calls/{call_sid}/recording.mp3"


def upload_transcript(practice_id: str, call_sid: str, transcript_text: str) -> str:
    """
    Upload call transcript to Azure Blob Storage.

    Returns the blob name (equivalent to S3 key) on success.
    Raises on error — caller decides whether to retry or log.
    """
    blob_name = transcript_key(practice_id, call_sid)

    if not settings.azure_storage_connection_string:
        logger.warning("Azure Storage not configured — skipping transcript upload")
        return blob_name

    client = _blob_client(blob_name)
    client.upload_blob(
        data=BytesIO(transcript_text.encode("utf-8")),
        overwrite=True,
        content_settings=_content_settings("text/plain; charset=utf-8"),
    )

    logger.info(
        f"Transcript uploaded: {settings.azure_storage_container}/{blob_name}"
    )
    return blob_name


def upload_recording_from_url(practice_id: str, call_sid: str, twilio_recording_url: str) -> str:
    """
    Fetch a Twilio call recording and store it in Azure Blob Storage.

    Twilio makes recordings available at a URL after the call ends.
    We fetch the audio and re-upload to our HIPAA-eligible Azure container
    so we never rely on Twilio's storage for PHI.

    Returns the blob name on success.
    """
    import httpx

    blob_name = recording_key(practice_id, call_sid)

    if not settings.azure_storage_connection_string:
        logger.warning("Azure Storage not configured — skipping recording upload")
        return blob_name

    # Fetch from Twilio (authenticated with account credentials)
    response = httpx.get(
        twilio_recording_url,
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        timeout=30.0,
    )
    response.raise_for_status()

    client = _blob_client(blob_name)
    client.upload_blob(
        data=BytesIO(response.content),
        overwrite=True,
        content_settings=_content_settings("audio/mpeg"),
    )

    logger.info(
        f"Recording uploaded: {settings.azure_storage_container}/{blob_name}"
    )
    return blob_name


def _content_settings(content_type: str):
    """Return Azure ContentSettings for a given MIME type."""
    from azure.storage.blob import ContentSettings
    return ContentSettings(content_type=content_type)
