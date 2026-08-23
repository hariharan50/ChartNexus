"""Composition root.

Plain constructor wiring — no DI framework. Every process (api, ingest, score,
realtime) builds one :class:`Container`, and handlers receive their
dependencies explicitly. Adapters are chosen here and nowhere else, which is
what keeps the broker, LLM, and identity providers swappable in tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType

import httpx

from marketcompass.bootstrap.settings import Settings, get_settings
from marketcompass.infrastructure.cache.redis.client import RedisClient
from marketcompass.infrastructure.persistence.postgresql.session import Database
from marketcompass.infrastructure.security.encryption import AesGcmCipher
from marketcompass.infrastructure.security.google_oauth import GoogleOAuthClient
from marketcompass.infrastructure.security.password_hasher import Argon2Hasher
from marketcompass.infrastructure.security.token_signer import JwtAccessTokenIssuer


@dataclass(slots=True)
class Container:
    """Owns every process-lifetime resource."""

    settings: Settings
    database: Database
    redis: RedisClient
    http: httpx.AsyncClient
    # Stateless and expensive to construct (Argon2 hashes a dummy password at
    # startup, JWT parses its key), so both are built once per process.
    password_hasher: Argon2Hasher
    access_tokens: JwtAccessTokenIssuer
    # Encrypts broker credentials at rest with AES-256-GCM. Key derivation runs
    # once here rather than on every repository construction.
    token_cipher: AesGcmCipher
    # Encrypts users' own LLM API keys at rest. Derived from the same configured
    # secret but under a distinct HKDF purpose, so an AI-key ciphertext can never
    # be decrypted in the broker context, or vice versa.
    ai_settings_cipher: AesGcmCipher
    # Encrypts users' messaging-channel secrets (e.g. Telegram bot tokens) at rest,
    # under its own HKDF purpose so it is isolated from the broker/AI ciphers.
    messaging_cipher: AesGcmCipher
    # None when no Google credentials are configured; only the two Google
    # routes care, and they fail with a clear message.
    google_oauth: GoogleOAuthClient | None

    @classmethod
    def create(cls, settings: Settings | None = None, *, use_db_pool: bool = True) -> Container:
        resolved = settings or get_settings()
        http = httpx.AsyncClient(
            timeout=resolved.request_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": "MarketCompass/0.1"},
        )
        return cls(
            settings=resolved,
            database=Database.create(resolved.database, use_pool=use_db_pool),
            redis=RedisClient.create(resolved.redis),
            http=http,
            password_hasher=Argon2Hasher(resolved.security),
            access_tokens=JwtAccessTokenIssuer(resolved.auth, resolved.security),
            token_cipher=AesGcmCipher.derive(
                resolved.security.encryption_key.get_secret_value(),
                previous_secrets=resolved.security.retired_encryption_keys,
            ),
            ai_settings_cipher=AesGcmCipher.derive(
                resolved.security.encryption_key.get_secret_value(),
                purpose="ai-settings",
                previous_secrets=resolved.security.retired_encryption_keys,
            ),
            messaging_cipher=AesGcmCipher.derive(
                resolved.security.encryption_key.get_secret_value(),
                purpose="messaging-credentials",
                previous_secrets=resolved.security.retired_encryption_keys,
            ),
            google_oauth=(
                GoogleOAuthClient(resolved.google, http) if resolved.google.enabled else None
            ),
        )

    async def aclose(self) -> None:
        """Release resources in reverse order of acquisition."""
        await self.http.aclose()
        await self.redis.close()
        await self.database.dispose()

    async def __aenter__(self) -> Container:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
