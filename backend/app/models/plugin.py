from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship
from ..db.session import Base


class Plugin(Base):
    __tablename__ = 'plugins'

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    name = Column(String(160), nullable=False)
    slug = Column(String(180), unique=True, nullable=False, index=True)
    summary = Column(Text, nullable=False, default='')
    category = Column(String(80), nullable=False, default='workflow')
    plugin_type = Column(String(80), nullable=False, default='module')
    author_name = Column(String(120), nullable=False, default='TokenFlow')
    icon = Column(String(500), nullable=False, default='')
    tags = Column(JSON, nullable=False, default=list)
    source = Column(JSON, nullable=False, default=dict)
    workspace_snapshot = Column(JSON, nullable=True)
    node_template_snapshot = Column(JSON, nullable=True)
    is_public = Column(Boolean, nullable=False, default=True)
    downloads = Column(Integer, nullable=False, default=0)
    installs = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship('User')
