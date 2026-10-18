"""        
    Application configuration for the Danube Chatbot Backend.

    This module contains non-secret application configuration required for all environments.
    
    For local development, sensitive values are loaded separately from the .env file using LocalSecrets.

    For deployed environments such as development, UAT, and production,
    sensitive values are retrieved from Azure Key Vault.

"""


from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    """
        Define and validate non-secret application configuration.

        These settings are available across all environments and control
        application behaviour without containing sensitive credentials.

        REQUIRED = postgres_url: str
        OPTIONAL = key_vault_url: str | None = None
        HAS DEFAULT = request_timeout_seconds: int = 10
    """

    app_name: str = "Danube Chatbot Backend"
    environment: Literal["local", "development", "uat", "production"]
    debug: bool = False

    # Azure Key Vault
    key_vault_url: str | None = None

    # Currency API
    currency_api_url: str = ""
    currency_cache_refresh_hours: int = 24
    currency_cache_ttl_seconds: int = 259200
    currency_api_cookie: str = ""

    # Correlation ID Header
    correlation_id_header: str = "X-Correlation-ID"

    # External APIs
    request_timeout_seconds: int = 10

    # Marketing API
    marketing_api_url: str = ""
    marketing_cache_ttl_seconds: int = 172800
    api_cache_refresh_hours: int = 12
    marketing_product_name: str = "Vendor"
    marketing_product_feature_name: str = "AMIRA"

    # Pinecone
    pinecone_index_name: str | None = None

    # Retry
    retry_attempts: int = 3
    retry_min_wait_seconds: float = 1
    retry_max_wait_seconds: float = 8

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

class LocalSecrets(BaseSettings):
    """
        Define sensitive values used only during local development.

        These values are loaded from the local .env file when the application
        is running with ENVIRONMENT=local.

        Deployed environments must retrieve the corresponding secrets from
        Azure Key Vault instead.
    """

    postgres_url: str
    redis_host: str
    redis_port: int
    pinecone_api_key: str
    applicationinsights_connection_string: str
    marketing_api_key: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )




@lru_cache
def get_settings() -> Settings:
    """
        Load and cache the application settings.

        The settings object is created once and reused throughout the application. 

        Returns:
            Settings: Validated and cached non-secret application configuration..
    """

    return Settings()

@lru_cache
def get_local_secrets() -> LocalSecrets:
    """
        Load, validate, and cache secrets for local development.

        This function should only be called when the application is running
        with ENVIRONMENT=local.

        Returns:
            LocalSecrets: Validated and cached local development secrets.
    """
    return LocalSecrets()


settings = get_settings()