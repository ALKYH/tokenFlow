import secrets
import hashlib
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from ..models.refresh_token import RefreshToken

# Default refresh token lifetime (days)
REFRESH_TOKEN_EXPIRE_DAYS = 7


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


async def create_refresh_token(session, user, expires_days: int = REFRESH_TOKEN_EXPIRE_DAYS):
    token = secrets.token_urlsafe(48)
    token_hash = _hash_token(token)
    now = datetime.utcnow()
    expires_at = now + timedelta(days=expires_days)
    rt = RefreshToken(token_hash=token_hash, user_id=user.id, created_at=now, expires_at=expires_at)
    session.add(rt)
    await session.commit()
    await session.refresh(rt)
    return token, rt


async def get_refresh_token_entry(session, token: str):
    token_hash = _hash_token(token)
    q = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    res = await session.execute(q)
    return res.scalars().first()


async def verify_refresh_token(session, token: str):
    entry = await get_refresh_token_entry(session, token)
    if not entry:
        return None
    if entry.revoked:
        return None
    if entry.expires_at < datetime.utcnow():
        return None
    return entry


async def revoke_refresh_token(session, token: str):
    entry = await get_refresh_token_entry(session, token)
    if not entry:
        return False
    entry.revoked = True
    session.add(entry)
    await session.commit()
    return True


async def rotate_refresh_token(session, old_token: str, user):
    # revoke old and create new
    await revoke_refresh_token(session, old_token)
    new_token, entry = await create_refresh_token(session, user)
    return new_token, entry
