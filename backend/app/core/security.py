from datetime import datetime, timedelta
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from jose import jwt, JWTError
from .config import SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES

ALGORITHM = 'HS256'


def _get_fernet() -> Fernet:
    digest = hashlib.sha256(SECRET_KEY.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({'exp': expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def encrypt_secret(value: str) -> str:
    return _get_fernet().encrypt(value.encode('utf-8')).decode('utf-8')


def decrypt_secret(value: str) -> str | None:
    try:
        return _get_fernet().decrypt(value.encode('utf-8')).decode('utf-8')
    except (InvalidToken, ValueError):
        return None
