from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship
from ..db.session import Base


class RoutingRule(Base):
    __tablename__ = 'routing_rules'

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    name = Column(String(180), nullable=False)
    category = Column(String(80), nullable=False, default='general')
    channel = Column(String(80), nullable=False, default='dashboard')
    matcher_type = Column(String(60), nullable=False, default='keyword')
    matcher_config = Column(JSON, nullable=False, default=dict)
    action_config = Column(JSON, nullable=False, default=dict)
    classifier_mode = Column(String(60), nullable=False, default='rule')
    priority = Column(Integer, nullable=False, default=100)
    enabled = Column(Boolean, nullable=False, default=True)
    is_public = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship('User')
