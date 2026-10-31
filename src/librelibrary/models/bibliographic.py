"""Bibliographic records, shared by everyone on an instance."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from librelibrary.db import Base, UTCDateTime, utcnow


class Work(Base):
    """An abstract book."""

    __tablename__ = "work"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(1000), index=True)
    original_language: Mapped[str | None] = mapped_column(String(35))
    first_published: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)

    editions: Mapped[list["Edition"]] = relationship(
        back_populates="work", cascade="all, delete-orphan", passive_deletes=True
    )
    contributions: Mapped[list["Contribution"]] = relationship(
        back_populates="work",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Contribution.position",
    )
    subjects: Mapped[list["Subject"]] = relationship(
        secondary="work_subject", order_by="Subject.id"
    )
    classifications: Mapped[list["Classification"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    series_entries: Mapped[list["SeriesEntry"]] = relationship(
        back_populates="work", cascade="all, delete-orphan", passive_deletes=True
    )


class Edition(Base):
    """A published form of a work."""

    __tablename__ = "edition"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_id: Mapped[int] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(1000))
    subtitle: Mapped[str | None] = mapped_column(String(1000))
    publisher: Mapped[str | None] = mapped_column(String(500))
    published: Mapped[str | None] = mapped_column(String(32))
    language: Mapped[str | None] = mapped_column(String(35))
    format: Mapped[str | None] = mapped_column(String(64))
    pages: Mapped[int | None]
    cover: Mapped[str | None] = mapped_column(String(2000))

    work: Mapped[Work] = relationship(back_populates="editions")
    contributions: Mapped[list["Contribution"]] = relationship(
        back_populates="edition",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Contribution.position",
    )
    identifiers: Mapped[list["Identifier"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class Person(Base):
    """An author or other contributor."""

    __tablename__ = "person"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), index=True)
    sort_name: Mapped[str | None] = mapped_column(String(500))
    external_ids: Mapped[str | None] = mapped_column(Text)


class Contribution(Base):
    """Links a person to a work or an edition, in order."""

    __tablename__ = "contribution"
    __table_args__ = (
        CheckConstraint("(work_id IS NULL) <> (edition_id IS NULL)", name="one_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), index=True
    )
    work_id: Mapped[int | None] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), index=True
    )
    edition_id: Mapped[int | None] = mapped_column(
        ForeignKey("edition.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(default=0)

    work: Mapped[Work | None] = relationship(back_populates="contributions")
    edition: Mapped[Edition | None] = relationship(back_populates="contributions")


class Series(Base):
    """A named series."""

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), index=True)


class SeriesEntry(Base):
    """A work's place in a series; the position is text, such as "2.5"."""

    __tablename__ = "series_entry"
    __table_args__ = (UniqueConstraint("series_id", "work_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    work_id: Mapped[int] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[str | None] = mapped_column(String(32))

    work: Mapped[Work] = relationship(back_populates="series_entries")


class Subject(Base):
    """A subject heading, unique per scheme and label."""

    __tablename__ = "subject"
    __table_args__ = (UniqueConstraint("scheme", "label"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scheme: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(500))


class WorkSubject(Base):
    """Links a subject to a work."""

    __tablename__ = "work_subject"

    work_id: Mapped[int] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), primary_key=True
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subject.id", ondelete="CASCADE"), primary_key=True
    )


class Classification(Base):
    """A class number for a work."""

    __tablename__ = "classification"
    __table_args__ = (UniqueConstraint("work_id", "scheme", "value"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("work.id", ondelete="CASCADE"))
    scheme: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(100))


class Identifier(Base):
    """An ID for an edition, unique per scheme and value."""

    __tablename__ = "identifier"
    __table_args__ = (UniqueConstraint("scheme", "value"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    edition_id: Mapped[int] = mapped_column(
        ForeignKey("edition.id", ondelete="CASCADE"), index=True
    )
    scheme: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(200))


class MetadataSource(Base):
    """Where an edition's metadata came from."""

    __tablename__ = "metadata_source"

    id: Mapped[int] = mapped_column(primary_key=True)
    edition_id: Mapped[int] = mapped_column(
        ForeignKey("edition.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str | None] = mapped_column(String(200))
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    license_note: Mapped[str | None] = mapped_column(String(500))
