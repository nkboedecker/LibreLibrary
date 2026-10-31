"""Personal records, owned by a user or a library."""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from librelibrary.db import Base, UTCDateTime, utcnow


class Library(Base):
    """A user's or household's collection."""

    __tablename__ = "library"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    default_privacy: Mapped[str] = mapped_column(String(16), default="private")
    editors_see_private: Mapped[bool] = mapped_column(default=True)


class LibraryMember(Base):
    """A user's role in a library; the owner has a row too."""

    __tablename__ = "library_member"

    library_id: Mapped[int] = mapped_column(
        ForeignKey("library.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(16))


class Copy(Base):
    """A physical or digital item someone owns."""

    __tablename__ = "copy"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("library.id", ondelete="CASCADE"), index=True
    )
    edition_id: Mapped[int] = mapped_column(
        ForeignKey("edition.id", ondelete="RESTRICT"), index=True
    )
    condition: Mapped[str | None] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(String(200))
    acquired: Mapped[date | None]
    source: Mapped[str | None] = mapped_column(String(200))
    price_minor: Mapped[int | None]
    currency: Mapped[str | None] = mapped_column(String(3))
    privacy: Mapped[str] = mapped_column(String(16))


class ReadingState(Base):
    """One reading of a work; a user may have several."""

    __tablename__ = "reading_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    work_id: Mapped[int] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16))
    started: Mapped[date | None]
    finished: Mapped[date | None]


class Rating(Base):
    """A user's rating of a work, in half stars from 1 to 10."""

    __tablename__ = "rating"
    __table_args__ = (
        UniqueConstraint("user_id", "work_id"),
        CheckConstraint("value BETWEEN 1 AND 10", name="value_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE")
    )
    work_id: Mapped[int] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), index=True
    )
    value: Mapped[int]
    privacy: Mapped[str] = mapped_column(String(16))


class Review(Base):
    """A user's review of a work."""

    __tablename__ = "review"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    work_id: Mapped[int] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    privacy: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Note(Base):
    """A user's note on a work."""

    __tablename__ = "note"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    work_id: Mapped[int] = mapped_column(
        ForeignKey("work.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    privacy: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Tag(Base):
    """A free tag, unique per library."""

    __tablename__ = "tag"
    __table_args__ = (UniqueConstraint("library_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("library.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(200))


class CopyTag(Base):
    """Links a tag to a copy."""

    __tablename__ = "copy_tag"

    copy_id: Mapped[int] = mapped_column(
        ForeignKey("copy.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class Shelf(Base):
    """A collection or shelf within a library."""

    __tablename__ = "shelf"
    __table_args__ = (UniqueConstraint("library_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("library.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32), default="shelf")


class ShelfItem(Base):
    """Links a copy to a shelf."""

    __tablename__ = "shelf_item"

    shelf_id: Mapped[int] = mapped_column(
        ForeignKey("shelf.id", ondelete="CASCADE"), primary_key=True
    )
    copy_id: Mapped[int] = mapped_column(
        ForeignKey("copy.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class Borrower(Base):
    """Someone a library lends to."""

    __tablename__ = "borrower"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("library.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    contact: Mapped[str | None] = mapped_column(String(320))


class Loan(Base):
    """One lending of a copy; a copy has at most one open loan."""

    __tablename__ = "loan"
    __table_args__ = (
        Index(
            "uq_loan_open_copy",
            "copy_id",
            unique=True,
            sqlite_where=text("returned IS NULL"),
            postgresql_where=text("returned IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    copy_id: Mapped[int] = mapped_column(
        ForeignKey("copy.id", ondelete="CASCADE"), index=True
    )
    borrower_id: Mapped[int] = mapped_column(
        ForeignKey("borrower.id", ondelete="RESTRICT"), index=True
    )
    lent: Mapped[date]
    due: Mapped[date | None]
    returned: Mapped[date | None]
