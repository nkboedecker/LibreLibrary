"""What a user records about a work: readings, ratings, reviews, and notes."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from librelibrary.authz.policy import (
    Action,
    Actor,
    OwnedResource,
    policy_action,
    require,
)
from librelibrary.authz.scoping import visible_responses
from librelibrary.db import utcnow
from librelibrary.errors import NotFound
from librelibrary.models import Note, Rating, ReadingState, Review, Work
from librelibrary.schemas import (
    RatingIn,
    ReadingStateIn,
    ReadingStatePatch,
    ResponseIn,
    ResponsePatch,
)
from librelibrary.services.common import (
    Listing,
    apply_changes,
    get_or_404,
    paginate,
)


def _own_reading(session: Session, actor: Actor, state_id: int) -> ReadingState:
    state = session.get(ReadingState, state_id)
    if state is None or state.user_id != actor.user_id:
        raise NotFound
    return state


@policy_action(Action.PERSONAL_READ)
def list_reading_states(
    session: Session, actor: Actor, work_id: int | None, limit: int, offset: int
) -> Listing[ReadingState]:
    """List the actor's readings, optionally of one work."""
    statement = (
        select(ReadingState)
        .where(ReadingState.user_id == actor.user_id)
        .order_by(ReadingState.id)
    )
    if work_id is not None:
        statement = statement.where(ReadingState.work_id == work_id)
    return paginate(session, statement, limit, offset)


@policy_action(Action.PERSONAL_WRITE)
def create_reading_state(
    session: Session, actor: Actor, payload: ReadingStateIn
) -> ReadingState:
    """Record a reading."""
    get_or_404(session, Work, payload.work_id)
    state = ReadingState(user_id=actor.user_id, **payload.model_dump())
    session.add(state)
    session.commit()
    return state


@policy_action(Action.PERSONAL_WRITE)
def update_reading_state(
    session: Session, actor: Actor, state_id: int, payload: ReadingStatePatch
) -> ReadingState:
    """Change one of the actor's readings."""
    state = _own_reading(session, actor, state_id)
    apply_changes(state, payload.model_dump(exclude_unset=True))
    session.commit()
    return state


@policy_action(Action.PERSONAL_WRITE)
def delete_reading_state(session: Session, actor: Actor, state_id: int) -> None:
    """Delete one of the actor's readings."""
    session.delete(_own_reading(session, actor, state_id))
    session.commit()


@policy_action(Action.PERSONAL_READ)
def list_ratings(
    session: Session, actor: Actor, work_id: int, limit: int, offset: int
) -> Listing[Rating]:
    """List the ratings of a work that the actor can see."""
    get_or_404(session, Work, work_id)
    statement = (
        select(Rating)
        .where(Rating.work_id == work_id, visible_responses(actor, Rating))
        .order_by(Rating.id)
    )
    return paginate(session, statement, limit, offset)


@policy_action(Action.PERSONAL_WRITE)
def set_rating(
    session: Session, actor: Actor, work_id: int, payload: RatingIn
) -> Rating:
    """Set the actor's rating of a work."""
    get_or_404(session, Work, work_id)
    rating = session.scalar(
        select(Rating).where(Rating.user_id == actor.user_id, Rating.work_id == work_id)
    )
    if rating is None:
        rating = Rating(user_id=actor.user_id, work_id=work_id, **payload.model_dump())
        session.add(rating)
    else:
        apply_changes(rating, payload.model_dump())
    session.commit()
    return rating


@policy_action(Action.PERSONAL_WRITE)
def delete_rating(session: Session, actor: Actor, work_id: int) -> None:
    """Delete the actor's rating of a work."""
    rating = session.scalar(
        select(Rating).where(Rating.user_id == actor.user_id, Rating.work_id == work_id)
    )
    if rating is None:
        raise NotFound
    session.delete(rating)
    session.commit()


def _visible_text[T: (Review, Note)](
    session: Session, actor: Actor, model: type[T], record_id: int
) -> T:
    record = session.scalar(
        select(model).where(model.id == record_id, visible_responses(actor, model))
    )
    if record is None:
        raise NotFound
    return record


def _list_text[T: (Review, Note)](  # noqa: PLR0913
    session: Session,
    actor: Actor,
    model: type[T],
    work_id: int,
    limit: int,
    offset: int,
) -> Listing[T]:
    get_or_404(session, Work, work_id)
    statement = (
        select(model)
        .where(model.work_id == work_id, visible_responses(actor, model))
        .order_by(model.id)
    )
    return paginate(session, statement, limit, offset)


def _create_text[T: (Review, Note)](
    session: Session, actor: Actor, model: type[T], work_id: int, payload: ResponseIn
) -> T:
    get_or_404(session, Work, work_id)
    record = model(
        user_id=actor.user_id,
        work_id=work_id,
        created_at=utcnow(),
        **payload.model_dump(),
    )
    session.add(record)
    session.commit()
    return record


def _update_text[T: (Review, Note)](
    session: Session,
    actor: Actor,
    model: type[T],
    record_id: int,
    payload: ResponsePatch,
) -> T:
    record = _visible_text(session, actor, model, record_id)
    require(actor, Action.PERSONAL_WRITE, OwnedResource(record.user_id))
    apply_changes(record, payload.model_dump(exclude_unset=True))
    session.commit()
    return record


def _delete_text[T: (Review, Note)](
    session: Session, actor: Actor, model: type[T], record_id: int
) -> None:
    record = _visible_text(session, actor, model, record_id)
    require(actor, Action.PERSONAL_WRITE, OwnedResource(record.user_id))
    session.delete(record)
    session.commit()


@policy_action(Action.PERSONAL_READ)
def list_reviews(
    session: Session, actor: Actor, work_id: int, limit: int, offset: int
) -> Listing[Review]:
    """List the reviews of a work that the actor can see."""
    return _list_text(session, actor, Review, work_id, limit, offset)


@policy_action(Action.PERSONAL_WRITE)
def create_review(
    session: Session, actor: Actor, work_id: int, payload: ResponseIn
) -> Review:
    """Write a review."""
    return _create_text(session, actor, Review, work_id, payload)


@policy_action(Action.PERSONAL_READ)
def get_review(session: Session, actor: Actor, review_id: int) -> Review:
    """Return a review the actor can see."""
    return _visible_text(session, actor, Review, review_id)


@policy_action(Action.PERSONAL_WRITE)
def update_review(
    session: Session, actor: Actor, review_id: int, payload: ResponsePatch
) -> Review:
    """Change the actor's review."""
    return _update_text(session, actor, Review, review_id, payload)


@policy_action(Action.PERSONAL_WRITE)
def delete_review(session: Session, actor: Actor, review_id: int) -> None:
    """Delete the actor's review."""
    _delete_text(session, actor, Review, review_id)


@policy_action(Action.PERSONAL_READ)
def list_notes(
    session: Session, actor: Actor, work_id: int, limit: int, offset: int
) -> Listing[Note]:
    """List the notes on a work that the actor can see."""
    return _list_text(session, actor, Note, work_id, limit, offset)


@policy_action(Action.PERSONAL_WRITE)
def create_note(
    session: Session, actor: Actor, work_id: int, payload: ResponseIn
) -> Note:
    """Write a note."""
    return _create_text(session, actor, Note, work_id, payload)


@policy_action(Action.PERSONAL_READ)
def get_note(session: Session, actor: Actor, note_id: int) -> Note:
    """Return a note the actor can see."""
    return _visible_text(session, actor, Note, note_id)


@policy_action(Action.PERSONAL_WRITE)
def update_note(
    session: Session, actor: Actor, note_id: int, payload: ResponsePatch
) -> Note:
    """Change the actor's note."""
    return _update_text(session, actor, Note, note_id, payload)


@policy_action(Action.PERSONAL_WRITE)
def delete_note(session: Session, actor: Actor, note_id: int) -> None:
    """Delete the actor's note."""
    _delete_text(session, actor, Note, note_id)
