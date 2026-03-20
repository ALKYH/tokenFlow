from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship
from ..db.session import Base


class UserSecret(Base):
    __tablename__ = 'user_secrets'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    provider = Column(String(120), nullable=False, default='openai')
    secret_name = Column(String(120), nullable=False, default='default')
    request_prefix = Column(String(500), nullable=False, default='')
    priority = Column(Integer, nullable=False, default=100)
    encrypted_api_key = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship('User')
