from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PolicyDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "policy_documents"
    
    topic: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "returns", "shipping", "refunds"
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    body: Mapped[str] = mapped_column(Text, nullable=False)  # raw source text
    
    # lazy="selectin" safely handles loading chunks automatically
    chunks: Mapped[list["PolicyChunk"]] = relationship(
        back_populates="document", 
        lazy="selectin", 
        cascade="all, delete-orphan"
    )


class PolicyChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "policy_chunks"
    
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("policy_documents.id", ondelete="CASCADE"),
        nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    
    document: Mapped["PolicyDocument"] = relationship(back_populates="chunks")
