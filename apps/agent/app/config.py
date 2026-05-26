from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── LLM: chain primary → fallbacks ──────────────────────────────
    # `llm_primary` puede ser: "ollama" | "anthropic" | "deepseek"
    # `llm_fallbacks` es una lista separada por comas en el mismo orden:
    #   ej: "deepseek,anthropic" → DeepSeek primero, luego Anthropic Haiku
    # La heurística determinista siempre se añade como último eslabón.
    llm_primary: str = "anthropic"
    llm_fallbacks: str = "anthropic"  # CSV; opcional

    # Anthropic Claude
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_fallback_model: str = "claude-haiku-4-5-20251001"

    # DeepSeek (API OpenAI-compatible). Para "Flash" o variantes, ajusta
    # `deepseek_model` al slug que publique el proveedor.
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # Ollama local (Gemma4, Llama3, Qwen, etc.)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:latest"

    # Circuit breaker
    circuit_failure_threshold: int = 3
    circuit_reset_seconds: float = 30.0
    circuit_per_call_timeout_seconds: float = 20.0
    circuit_min_confidence: float = 0.5

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"

    installer_notification_webhook: str = ""
    installer_whatsapp_to: str = ""

    database_path: str = "data/rai.db"
    company_name: str = "Raidasl"
    privacy_policy_url: str = "https://raidasl.example/privacidad"

    admin_api_key: str = ""

    def llm_fallbacks_csv(self) -> list[str]:
        return [s.strip() for s in (self.llm_fallbacks or "").split(",") if s.strip()]


settings = Settings()
