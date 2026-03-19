from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ..db.session import AsyncSessionLocal
from ..models.user import User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


async def get_user_by_email(session, email: str):
    q = select(User).where(User.email == email)
    res = await session.execute(q)
    return res.scalars().first()


async def create_user(session, email: str, password: str):
    user = User(email=email, hashed_password=get_password_hash(password))
    session.add(user)
    try:
        await session.commit()
        await session.refresh(user)
        return user
    except IntegrityError:
        await session.rollback()
        return None


async def authenticate_user(session, email: str, password: str):
    user = await get_user_by_email(session, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
