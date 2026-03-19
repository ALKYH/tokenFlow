from sqlalchemy import JSON, Column, Integer, String, Boolean, DateTime, func
from ..db.session import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(320), unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    display_name = Column(String(120), nullable=False, default='TokenFlow User')
    bio = Column(String(500), nullable=False, default='')
    avatar_url = Column(String(500), nullable=False, default='')
    preferences = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
