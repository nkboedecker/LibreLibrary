"""Request and response shapes, shared by the API and later surfaces."""

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from librelibrary.authz.policy import LibraryRole, Privacy, Role, Scope


def _no_nul(value: str) -> str:
    """Refuse NUL characters, which PostgreSQL can't store."""
    if "\x00" in value:
        raise ValueError("NUL characters aren't allowed")  # noqa: TRY003
    return value


def _lowercase(value: str) -> str:
    """Normalize case in the application, so both databases behave the same."""
    return value.strip().lower()


_Clean = AfterValidator(_no_nul)
Str3 = Annotated[str, StringConstraints(min_length=3, max_length=3), _Clean]
Str32 = Annotated[str, StringConstraints(min_length=1, max_length=32), _Clean]
Str35 = Annotated[str, StringConstraints(min_length=1, max_length=35), _Clean]
Str64 = Annotated[str, StringConstraints(min_length=1, max_length=64), _Clean]
Str100 = Annotated[str, StringConstraints(min_length=1, max_length=100), _Clean]
Str200 = Annotated[str, StringConstraints(min_length=1, max_length=200), _Clean]
Str320 = Annotated[str, StringConstraints(min_length=1, max_length=320), _Clean]
Str500 = Annotated[str, StringConstraints(min_length=1, max_length=500), _Clean]
Str1000 = Annotated[str, StringConstraints(min_length=1, max_length=1000), _Clean]
Str2000 = Annotated[str, StringConstraints(min_length=1, max_length=2000), _Clean]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=200_000), _Clean]
Password = Annotated[str, StringConstraints(min_length=1, max_length=1024), _Clean]
NewPassword = Annotated[str, StringConstraints(min_length=12, max_length=1024), _Clean]
Username = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$"),
    AfterValidator(_lowercase),
]
Email = Annotated[
    str,
    StringConstraints(max_length=320, pattern=r"^[^@\s\x00]+@[^@\s\x00]+$"),
    AfterValidator(_lowercase),
]
Id = Annotated[int, Field(ge=1, le=2_147_483_647)]
Count = Annotated[int, Field(ge=0, le=2_147_483_647)]
StarValue = Annotated[int, Field(ge=1, le=10)]


class _In(BaseModel):
    """A request body: unknown fields are refused and enums become plain text."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class _Out(BaseModel):
    """A response body, read from a database record."""

    model_config = ConfigDict(from_attributes=True)


class ErrorOut(BaseModel):
    """An error response."""

    detail: str


class Health(BaseModel):
    """The response of the health endpoint."""

    status: str
    version: str


class Page[T](_Out):
    """One page of a list."""

    items: list[T]
    total: int
    limit: int
    offset: int


# Accounts and tokens


class LoginIn(_In):
    """Sign in with a password to get a bearer token."""

    username: Username
    password: Password
    token_name: Str100 = "sign-in"  # noqa: S105
    scopes: list[Scope] = [Scope.LIBRARY_READ, Scope.LIBRARY_WRITE]


class TokenIn(_In):
    """Create a personal access token."""

    name: Str100
    scopes: list[Scope]
    expires_at: AwareDatetime | None = None


class TokenOut(_Out):
    """A token, without its secret."""

    id: int
    name: str
    display_prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class TokenCreatedOut(TokenOut):
    """A new token. This is the only time that its secret is shown."""

    token: str


class UserOut(_Out):
    """A user account."""

    id: int
    username: str
    email: str | None
    display_name: str
    role: Role
    is_active: bool
    created_at: datetime


class UserIn(_In):
    """Create a user."""

    username: Username
    display_name: Str200
    password: NewPassword
    email: Email | None = None
    role: Role = Role.MEMBER


class UserPatch(_In):
    """Change a user."""

    display_name: Str200 | None = None
    email: Email | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: NewPassword | None = None


class PasswordChangeIn(_In):
    """Change your own password."""

    current_password: Password
    new_password: NewPassword


# Catalog


class PersonIn(_In):
    """Create a person."""

    name: Str500
    sort_name: Str500 | None = None
    external_ids: LongText | None = None


class PersonPatch(_In):
    """Change a person."""

    name: Str500 | None = None
    sort_name: Str500 | None = None
    external_ids: LongText | None = None


class PersonOut(_Out):
    """A person."""

    id: int
    name: str
    sort_name: str | None
    external_ids: str | None


class SeriesIn(_In):
    """Create or rename a series."""

    name: Str500


class SeriesOut(_Out):
    """A series."""

    id: int
    name: str


class ContributionIn(_In):
    """A person's part in a work or edition."""

    person_id: Id
    role: Str32 = "author"
    position: Count = 0


class ContributionOut(_Out):
    """A person's part in a work or edition."""

    person_id: int
    role: str
    position: int


class SubjectIn(_In):
    """A subject heading."""

    scheme: Str32 = "free"
    label: Str500


class SubjectOut(_Out):
    """A subject heading."""

    scheme: str
    label: str


class ClassificationIn(_In):
    """A class number."""

    scheme: Str32
    value: Str100


class ClassificationOut(_Out):
    """A class number."""

    scheme: str
    value: str


class SeriesEntryIn(_In):
    """A work's place in a series."""

    series_id: Id
    position: Str32 | None = None


class SeriesEntryOut(_Out):
    """A work's place in a series."""

    series_id: int
    position: str | None


class WorkIn(_In):
    """Create a work."""

    title: Str1000
    original_language: Str35 | None = None
    first_published: Str32 | None = None
    description: LongText | None = None
    contributions: list[ContributionIn] = []
    subjects: list[SubjectIn] = []
    classifications: list[ClassificationIn] = []
    series_entries: list[SeriesEntryIn] = []


class WorkPatch(_In):
    """Change a work; a list that is present replaces the old list."""

    title: Str1000 | None = None
    original_language: Str35 | None = None
    first_published: Str32 | None = None
    description: LongText | None = None
    contributions: list[ContributionIn] | None = None
    subjects: list[SubjectIn] | None = None
    classifications: list[ClassificationIn] | None = None
    series_entries: list[SeriesEntryIn] | None = None


class WorkOut(_Out):
    """A work."""

    id: int
    title: str
    original_language: str | None
    first_published: str | None
    description: str | None
    contributions: list[ContributionOut]
    subjects: list[SubjectOut]
    classifications: list[ClassificationOut]
    series_entries: list[SeriesEntryOut]


class IdentifierIn(_In):
    """An ID for an edition."""

    scheme: Str32
    value: Str200


class IdentifierOut(_Out):
    """An ID for an edition."""

    scheme: str
    value: str


class EditionIn(_In):
    """Create an edition."""

    title: Str1000 | None = None
    subtitle: Str1000 | None = None
    publisher: Str500 | None = None
    published: Str32 | None = None
    language: Str35 | None = None
    format: Str64 | None = None
    pages: Count | None = None
    cover: Str2000 | None = None
    contributions: list[ContributionIn] = []
    identifiers: list[IdentifierIn] = []


class EditionPatch(_In):
    """Change an edition; a list that is present replaces the old list."""

    title: Str1000 | None = None
    subtitle: Str1000 | None = None
    publisher: Str500 | None = None
    published: Str32 | None = None
    language: Str35 | None = None
    format: Str64 | None = None
    pages: Count | None = None
    cover: Str2000 | None = None
    contributions: list[ContributionIn] | None = None
    identifiers: list[IdentifierIn] | None = None


class EditionOut(_Out):
    """An edition."""

    id: int
    work_id: int
    title: str | None
    subtitle: str | None
    publisher: str | None
    published: str | None
    language: str | None
    format: str | None
    pages: int | None
    cover: str | None
    contributions: list[ContributionOut]
    identifiers: list[IdentifierOut]


# Libraries


class LibraryIn(_In):
    """Create a library."""

    name: Str200
    default_privacy: Privacy = Privacy.PRIVATE
    editors_see_private: bool = True


class LibraryPatch(_In):
    """Change a library."""

    name: Str200 | None = None
    default_privacy: Privacy | None = None
    editors_see_private: bool | None = None


class LibraryOut(_Out):
    """A library."""

    id: int
    owner_id: int
    name: str
    default_privacy: Privacy
    editors_see_private: bool


class MemberIn(_In):
    """Give a user a role in a library. A library has one owner."""

    role: LibraryRole


class MemberOut(_Out):
    """A user's role in a library."""

    user_id: int
    role: LibraryRole


class CopyIn(_In):
    """Add a copy to a library."""

    library_id: Id
    edition_id: Id
    condition: Str64 | None = None
    location: Str200 | None = None
    acquired: date | None = None
    source: Str200 | None = None
    price_minor: Count | None = None
    currency: Str3 | None = None
    privacy: Privacy | None = None


class CopyPatch(_In):
    """Change a copy."""

    condition: Str64 | None = None
    location: Str200 | None = None
    acquired: date | None = None
    source: Str200 | None = None
    price_minor: Count | None = None
    currency: Str3 | None = None
    privacy: Privacy | None = None


class CopyOut(_Out):
    """A copy."""

    id: int
    library_id: int
    edition_id: int
    condition: str | None
    location: str | None
    acquired: date | None
    source: str | None
    price_minor: int | None
    currency: str | None
    privacy: Privacy


class TagNamesIn(_In):
    """The full set of tags for a copy."""

    names: list[Str200]


class TagIn(_In):
    """Create a tag."""

    name: Str200


class TagOut(_Out):
    """A tag."""

    id: int
    library_id: int
    name: str


class ShelfIn(_In):
    """Create a shelf."""

    name: Str200
    kind: Str32 = "shelf"


class ShelfPatch(_In):
    """Change a shelf."""

    name: Str200 | None = None
    kind: Str32 | None = None


class ShelfOut(_Out):
    """A shelf."""

    id: int
    library_id: int
    name: str
    kind: str


class BorrowerIn(_In):
    """Create a borrower."""

    name: Str200
    contact: Str320 | None = None


class BorrowerPatch(_In):
    """Change a borrower."""

    name: Str200 | None = None
    contact: Str320 | None = None


class BorrowerOut(_Out):
    """Someone a library lends to."""

    id: int
    library_id: int
    name: str
    contact: str | None


class LoanIn(_In):
    """Lend a copy."""

    copy_id: Id
    borrower_id: Id
    lent: date
    due: date | None = None


class LoanReturnIn(_In):
    """Record a return."""

    returned: date


class LoanOut(_Out):
    """One lending of a copy."""

    id: int
    copy_id: int
    borrower_id: int
    lent: date
    due: date | None
    returned: date | None


# Personal responses


READING_STATUS_PATTERN = r"^(want|reading|finished|abandoned)$"
Status = Annotated[str, StringConstraints(pattern=READING_STATUS_PATTERN)]


class ReadingStateIn(_In):
    """Record a reading of a work."""

    work_id: Id
    status: Status
    started: date | None = None
    finished: date | None = None


class ReadingStatePatch(_In):
    """Change a reading."""

    status: Status | None = None
    started: date | None = None
    finished: date | None = None


class ReadingStateOut(_Out):
    """One reading of a work."""

    id: int
    work_id: int
    status: str
    started: date | None
    finished: date | None


class RatingIn(_In):
    """Rate a work, in half stars from 1 to 10."""

    value: StarValue
    privacy: Privacy = Privacy.PRIVATE


class RatingOut(_Out):
    """A rating."""

    id: int
    user_id: int
    work_id: int
    value: int
    privacy: Privacy


class ResponseIn(_In):
    """Write a review or note."""

    text: LongText
    privacy: Privacy = Privacy.PRIVATE


class ResponsePatch(_In):
    """Change a review or note."""

    text: LongText | None = None
    privacy: Privacy | None = None


class ResponseOut(_Out):
    """A review or note."""

    id: int
    user_id: int
    work_id: int
    text: str
    privacy: Privacy
    created_at: datetime


# Administration


class AuditEventOut(_Out):
    """A security-relevant event."""

    id: int
    at: datetime
    actor_user_id: int | None
    action: str
    target: str | None
    detail: dict[str, Any]


class SettingIn(_In):
    """Set a run-time setting."""

    value: Any


class SettingOut(_Out):
    """A run-time setting."""

    key: str
    value: Any
    updated_at: datetime
