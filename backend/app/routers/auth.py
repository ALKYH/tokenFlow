from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from ..deps import get_current_user, get_optional_user, get_session
from ..services.user_service import authenticate_user, create_user
from ..schemas.user import Token, UserCreate, UserRead
from ..core.security import create_access_token
from ..services.token_service import create_refresh_token, revoke_refresh_token, verify_refresh_token

router = APIRouter(prefix='/api/auth', tags=['auth'])
compat_router = APIRouter(prefix='/auth', tags=['auth-compat'])


class CompatLoginBody(BaseModel):
    userName: str = Field(min_length=1)
    password: str = Field(min_length=1)


class CompatRefreshBody(BaseModel):
    refreshToken: str = Field(min_length=1)


def _compat_success(data):
    return {'code': '0000', 'msg': 'ok', 'data': data}


def _compat_fail(code: str, msg: str):
    return {'code': code, 'msg': msg, 'data': None}


def _resolve_user_roles(user) -> list[str]:
    preferences = user.preferences or {}
    role_config = preferences.get('roles')
    if isinstance(role_config, list):
        roles = [str(item).strip() for item in role_config if str(item).strip()]
        if roles:
            return roles

    normalized_name = (user.display_name or '').strip().lower()
    if normalized_name in {'super', 'soybean'}:
        return ['R_SUPER']
    if normalized_name == 'admin':
        return ['R_ADMIN']
    return ['R_USER']


def _resolve_user_buttons(user) -> list[str]:
    preferences = user.preferences or {}
    button_config = preferences.get('buttons')
    if isinstance(button_config, list):
        buttons = [str(item).strip() for item in button_config if str(item).strip()]
        if buttons:
            return buttons
    return ['B_DASHBOARD', 'B_MARKETPLACE', 'B_ROUTING', 'B_INBOX', 'B_EDITOR']


def _build_frontend_user_info(user):
    display_name = (user.display_name or '').strip() or user.email.split('@', 1)[0]
    return {
        'userId': str(user.id),
        'userName': display_name,
        'roles': _resolve_user_roles(user),
        'buttons': _resolve_user_buttons(user)
    }


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


@compat_router.post('/login')
async def compat_login(payload: CompatLoginBody, session=Depends(get_session)):
    user = await authenticate_user(session, payload.userName, payload.password)
    if not user:
        return _compat_fail('10001', 'Incorrect credentials')

    access_token = create_access_token({'sub': user.email})
    refresh_token, _ = await create_refresh_token(session, user)
    return _compat_success({'token': access_token, 'refreshToken': refresh_token})


@compat_router.get('/getUserInfo')
async def compat_get_user_info(user=Depends(get_optional_user)):
    if not user:
        return _compat_fail('8888', 'Not authenticated')
    return _compat_success(_build_frontend_user_info(user))


@compat_router.post('/refreshToken')
async def compat_refresh_token(payload: CompatRefreshBody, session=Depends(get_session)):
    entry = await verify_refresh_token(session, payload.refreshToken)
    if not entry or not entry.user:
        return _compat_fail('8888', 'Invalid or expired refresh token')

    user = entry.user
    new_refresh_token, _ = await create_refresh_token(session, user)
    await revoke_refresh_token(session, payload.refreshToken)
    access_token = create_access_token({'sub': user.email})
    return _compat_success({'token': access_token, 'refreshToken': new_refresh_token})


@compat_router.get('/error')
async def compat_error(
    code: str = Query(default='500'),
    msg: str = Query(default='custom backend error')
):
    return _compat_fail(code, msg)
