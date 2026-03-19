from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .db.session import AsyncSessionLocal
from .services.user_service import get_user_by_email
from .core.security import verify_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_session():
    async with AsyncSessionLocal() as s:
        yield s


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), session=Depends(get_session)):
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail='Not authenticated')
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail='Invalid token')
    email = payload.get('sub')
    if not email:
        raise HTTPException(status_code=401, detail='Invalid token payload')
    user = await get_user_by_email(session, email)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session=Depends(get_session)
):
    if not credentials or not credentials.credentials:
        return None
    payload = verify_token(credentials.credentials)
    if not payload:
        return None
    email = payload.get('sub')
    if not email:
        return None
    return await get_user_by_email(session, email)
