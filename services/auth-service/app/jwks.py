from fastapi import APIRouter
from jose import jwk

from app.keys import get_signing_keys

router = APIRouter(tags=["JWKS"])


@router.get("/.well-known/jwks.json")
async def get_jwks() -> dict:
    keys = get_signing_keys()
    public_key = jwk.construct(keys.public_pem, algorithm="RS256")
    key_dict = public_key.to_dict()
    key_dict.update({"kid": keys.kid, "use": "sig", "alg": "RS256"})
    return {"keys": [key_dict]}
