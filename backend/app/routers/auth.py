from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from ..deps import get_session, get_current_user
from ..services.user_service import create_user, authenticate_user
from ..schemas.user import UserCreate, UserRead, Token
from ..core.security import create_access_token
from ..services.token_service import create_refresh_token, revoke_refresh_token, verify_refresh_token

router = APIRouter(prefix='/api/auth')


@router.post('/register', response_model=UserRead)
async def register(user: UserCreate, session=Depends(get_session)):
    existing = await create_user(session, user.email, user.password)
    if not existing:
        # create_user returns None if email exists because of integrity error
        raise HTTPException(status_code=400, detail='Email already registered')
    return existing


@router.post('/login', response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends(), session=Depends(get_session)):
    user = await authenticate_user(session, form.username, form.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Incorrect credentials')
    access_token = create_access_token({'sub': user.email})
    refresh_token, _ = await create_refresh_token(session, user)
    return {'access_token': access_token, 'token_type': 'bearer', 'refresh_token': refresh_token}


@router.post('/refresh', response_model=Token)
async def refresh(body: dict, session=Depends(get_session)):
    refresh_token = body.get('refresh_token')
    if not refresh_token:
        raise HTTPException(status_code=400, detail='refresh_token required')
    entry = await verify_refresh_token(session, refresh_token)
    if not entry:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid or expired refresh token')
    user = entry.user
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found for refresh token')
    # create new refresh token and revoke old
    new_refresh, _ = await create_refresh_token(session, user)
    await revoke_refresh_token(session, refresh_token)
    access_token = create_access_token({'sub': user.email})
    return {'access_token': access_token, 'token_type': 'bearer', 'refresh_token': new_refresh}


@router.post('/logout')
async def logout(body: dict, session=Depends(get_session)):
    refresh_token = body.get('refresh_token')
    if not refresh_token:
        raise HTTPException(status_code=400, detail='refresh_token required')
    ok = await revoke_refresh_token(session, refresh_token)
    if not ok:
        raise HTTPException(status_code=404, detail='Refresh token not found')
    return {'detail': 'logged out'}


@router.get('/me', response_model=UserRead)
async def me(current=Depends(get_current_user)):
    return current
