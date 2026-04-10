from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from ..models.user import User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


async def get_user_by_email(session, email: str):
    normalized_email = (email or '').strip().lower()
    if not normalized_email:
        return None
    q = select(User).where(func.lower(User.email) == normalized_email)
    res = await session.execute(q)
    return res.scalars().first()


async def get_user_by_login(session, login: str):
    normalized_login = (login or '').strip().lower()
    if not normalized_login:
        return None

    email_local_part = normalized_login.split('@', 1)[0]
    q = select(User).where(
        or_(
            func.lower(User.email) == normalized_login,
            func.lower(User.display_name) == normalized_login,
            func.lower(User.email).like(f'{email_local_part}@%')
        )
    ).order_by(User.id.asc())
    res = await session.execute(q)
    return res.scalars().first()


async def create_user(session, email: str, password: str, display_name: str | None = None):
    normalized_email = (email or '').strip().lower()
    fallback_name = normalized_email.split('@', 1)[0] if '@' in normalized_email else normalized_email
    safe_display_name = (display_name or fallback_name or 'TokenFlow User').strip() or 'TokenFlow User'
    user = User(email=normalized_email, hashed_password=get_password_hash(password), display_name=safe_display_name)
    session.add(user)
    try:
        await session.commit()
        await session.refresh(user)
        return user
    except IntegrityError:
        await session.rollback()
        return None


async def authenticate_user(session, login: str, password: str):
    user = await get_user_by_login(session, login)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
