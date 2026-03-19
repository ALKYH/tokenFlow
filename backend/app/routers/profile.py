from sqlalchemy import select
from fastapi import APIRouter, Depends
from ..core.security import encrypt_secret
from ..deps import get_current_user, get_session
from ..models.user_secret import UserSecret
from ..schemas.profile import ProfileRead, ProfileUpdate

router = APIRouter(prefix='/api/profile', tags=['profile'])


@router.get('/me', response_model=ProfileRead)
async def get_my_profile(session=Depends(get_session), user=Depends(get_current_user)):
    secret = await session.scalar(select(UserSecret).where(UserSecret.user_id == user.id, UserSecret.is_active.is_(True)))
    return ProfileRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        bio=user.bio,
        avatar_url=user.avatar_url,
        preferences=user.preferences or {},
        api_provider=secret.provider if secret else None,
        has_api_key=bool(secret),
        is_active=user.is_active
    )


@router.patch('/me', response_model=ProfileRead)
async def update_my_profile(payload: ProfileUpdate, session=Depends(get_session), user=Depends(get_current_user)):
    user.display_name = payload.display_name
    user.bio = payload.bio
    user.avatar_url = payload.avatar_url
    user.preferences = payload.preferences or {}
    session.add(user)
    if payload.api_key:
        secret = await session.scalar(select(UserSecret).where(UserSecret.user_id == user.id))
        if not secret:
            secret = UserSecret(user_id=user.id, provider=payload.api_provider or 'openai', encrypted_api_key=encrypt_secret(payload.api_key))
        else:
            secret.provider = payload.api_provider or secret.provider
            secret.encrypted_api_key = encrypt_secret(payload.api_key)
            secret.is_active = True
        session.add(secret)
    await session.commit()
    await session.refresh(user)
    return await get_my_profile(session=session, user=user)
