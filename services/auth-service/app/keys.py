from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import get_settings


@dataclass(frozen=True)
class SigningKeys:
    private_pem: str
    public_pem: str
    kid: str


def _generate_ephemeral_keys(kid: str) -> SigningKeys:
    """
    Generate an in-memory RSA keypair for local development and tests.

    The keypair does not survive a process restart, so any tokens issued
    before a restart will fail JWKS verification afterwards. Production
    deployments must set jwt_private_key_path / jwt_public_key_path to a
    persisted keypair (see scripts/generate_jwt_keypair.py).
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return SigningKeys(private_pem=private_pem, public_pem=public_pem, kid=kid)


_NON_PRODUCTION_ENVS = {"development", "dev", "test", "testing", "local"}


@lru_cache
def get_signing_keys() -> SigningKeys:
    settings = get_settings()
    private_path = Path(settings.jwt_private_key_path)
    public_path = Path(settings.jwt_public_key_path)

    if private_path.exists() and public_path.exists():
        return SigningKeys(
            private_pem=private_path.read_text(encoding="ascii"),
            public_pem=public_path.read_text(encoding="ascii"),
            kid=settings.jwt_kid,
        )

    if settings.app_env.lower() not in _NON_PRODUCTION_ENVS:
        raise RuntimeError(
            f"JWT signing keys not found at {private_path} / {public_path}. "
            "Generate a persisted keypair with scripts/generate_jwt_keypair.py "
            "and mount it before starting the service outside of "
            "development/test — falling back to an ephemeral in-memory key "
            "would break JWKS verification across restarts and replicas."
        )

    return _generate_ephemeral_keys(settings.jwt_kid)
