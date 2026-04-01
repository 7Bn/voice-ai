from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/voice_ai"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    anthropic_api_key: str = ""
    deepgram_api_key: str = ""
    elevenlabs_api_key: str = ""
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_sip_host: str = ""       # e.g. abc123.sip.livekit.cloud — from livekit_setup.py
    livekit_sip_trunk_id: str = ""   # set after running livekit_setup.py
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket: str = ""
    environment: str = "development"
    secret_key: str = "change-me-in-production"
    # Outbound notifications (NotifyAdapter)
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "noreply@yourvoiceai.com"
    twilio_sms_from: str = ""  # E.164 number to send SMS from


settings = Settings()
