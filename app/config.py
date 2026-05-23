from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"

    installer_notification_webhook: str = ""
    installer_whatsapp_to: str = ""

    database_path: str = "data/rai.db"
    company_name: str = "Raidasl"
    privacy_policy_url: str = "https://raidasl.example/privacidad"


settings = Settings()
