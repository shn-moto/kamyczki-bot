from datetime import datetime
from sqlalchemy import Column, Integer, Text, DateTime, Float, String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536))
    doc_metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Stone(Base):
    __tablename__ = "stones"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    photo_file_id = Column(String(255), nullable=False)
    embedding = Column(Vector(512))  # CLIP ViT-B/32 produces 512-dim vectors
    registered_by_user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationship to history
    history = relationship("StoneHistory", back_populates="stone", order_by="desc(StoneHistory.created_at)")


class StoneHistory(Base):
    __tablename__ = "stone_history"

    id = Column(Integer, primary_key=True)
    stone_id = Column(Integer, ForeignKey("stones.id"), nullable=False)
    telegram_user_id = Column(Integer, nullable=False)
    photo_file_id = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    zip_code = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationship to stone
    stone = relationship("Stone", back_populates="history")


class UserSettings(Base):
    __tablename__ = "user_settings"

    telegram_user_id = Column(Integer, primary_key=True)
    language = Column(String(10), default="pl")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
