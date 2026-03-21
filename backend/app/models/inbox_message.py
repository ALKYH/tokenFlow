from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship
from ..db.session import Base


class InboxMessage(Base):
    __tablename__ = 'inbox_messages'

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    title = Column(String(180), nullable=False)
    body = Column(Text, nullable=False, default='')
    category = Column(String(80), nullable=False, default='system')
    channel = Column(String(80), nullable=False, default='dashboard')
    source = Column(String(120), nullable=False, default='system')
    is_read = Column(Boolean, nullable=False, default=False)
    attachments = Column(JSON, nullable=False, default=list)
    extra = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship('User')
