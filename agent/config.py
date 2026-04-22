from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # LLM
    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen3-235b-a22b"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # Observability
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Email
    resend_api_key: str = ""
    resend_from_email: str = "outreach@example.com"
    mailersend_api_key: str = ""
    email_webhook_url: str = ""

    # SMS (Africa's Talking)
    africastalking_username: str = "sandbox"
    africastalking_api_key: str = ""
    africastalking_shortcode: str = ""
    sms_webhook_url: str = ""

    # HubSpot
    hubspot_access_token: str = ""
    hubspot_portal_id: str = ""

    # Cal.com
    calcom_api_key: str = ""
    calcom_base_url: str = "http://localhost:3000"
    calcom_event_type_id: str = ""

    # Safety — MUST be False (staff sink) by default
    live_mode: bool = False
    staff_sink_email: str = "staff-sink@10academy.org"
    staff_sink_sms: str = "+251900000000"

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    secret_key: str = "change-me"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
