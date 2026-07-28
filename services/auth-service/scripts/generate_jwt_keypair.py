"""
Generate a persistent RSA keypair for signing JWT access tokens.

Run from the auth-service directory:

    python scripts/generate_jwt_keypair.py

Writes keys/jwt_private_key.pem and keys/jwt_public_key.pem (paths matching
the JWT_PRIVATE_KEY_PATH / JWT_PUBLIC_KEY_PATH defaults in app/config.py).
Without these files, the service falls back to an ephemeral keypair that is
regenerated on every restart, invalidating all outstanding access tokens.
"""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEYS_DIR = Path(__file__).resolve().parent.parent / "keys"
PRIVATE_KEY_PATH = KEYS_DIR / "jwt_private_key.pem"
PUBLIC_KEY_PATH = KEYS_DIR / "jwt_public_key.pem"


def main() -> None:
    if PRIVATE_KEY_PATH.exists() or PUBLIC_KEY_PATH.exists():
        raise SystemExit(
            f"Refusing to overwrite existing keys in {KEYS_DIR}. "
            "Remove them first if you intend to rotate."
        )

    KEYS_DIR.mkdir(parents=True, exist_ok=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    PRIVATE_KEY_PATH.write_bytes(private_pem)
    PUBLIC_KEY_PATH.write_bytes(public_pem)

    print(f"Wrote {PRIVATE_KEY_PATH}")
    print(f"Wrote {PUBLIC_KEY_PATH}")
    print("Keep the private key secret; it is gitignored by default.")


if __name__ == "__main__":
    main()
