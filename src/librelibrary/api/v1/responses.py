"""Readings, ratings, reviews, and notes."""

from fastapi import APIRouter, status

from librelibrary.api.deps import (
    CurrentActor,
    DbSession,
    Limit,
    Offset,
    PathId,
    QueryId,
)
from librelibrary.schemas import (
    Page,
    RatingIn,
    RatingOut,
    ReadingStateIn,
    ReadingStateOut,
    ReadingStatePatch,
    ResponseIn,
    ResponseOut,
    ResponsePatch,
)
from librelibrary.services import responses

router = APIRouter(tags=["responses"])
_NO_CONTENT = status.HTTP_204_NO_CONTENT
_CREATED = status.HTTP_201_CREATED


@router.get("/reading-states", operation_id="reading_states_list")
def list_reading_states(
    session: DbSession,
    actor: CurrentActor,
    work_id: QueryId = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[ReadingStateOut]:
    """List your readings, optionally of one work."""
    return Page[ReadingStateOut].model_validate(
        responses.list_reading_states(session, actor, work_id, limit, offset)
    )


@router.post(
    "/reading-states", operation_id="reading_states_create", status_code=_CREATED
)
def create_reading_state(
    payload: ReadingStateIn, session: DbSession, actor: CurrentActor
) -> ReadingStateOut:
    """Record a reading."""
    return ReadingStateOut.model_validate(
        responses.create_reading_state(session, actor, payload)
    )


@router.patch("/reading-states/{state_id}", operation_id="reading_states_update")
def update_reading_state(
    state_id: PathId,
    payload: ReadingStatePatch,
    session: DbSession,
    actor: CurrentActor,
) -> ReadingStateOut:
    """Change one of your readings."""
    return ReadingStateOut.model_validate(
        responses.update_reading_state(session, actor, state_id, payload)
    )


@router.delete(
    "/reading-states/{state_id}",
    operation_id="reading_states_delete",
    status_code=_NO_CONTENT,
)
def delete_reading_state(
    state_id: PathId, session: DbSession, actor: CurrentActor
) -> None:
    """Delete one of your readings."""
    responses.delete_reading_state(session, actor, state_id)


@router.get("/works/{work_id}/ratings", operation_id="ratings_list")
def list_ratings(
    work_id: PathId,
    session: DbSession,
    actor: CurrentActor,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[RatingOut]:
    """List the ratings of a work that you can see."""
    return Page[RatingOut].model_validate(
        responses.list_ratings(session, actor, work_id, limit, offset)
    )


@router.put("/works/{work_id}/rating", operation_id="ratings_set")
def set_rating(
    work_id: PathId, payload: RatingIn, session: DbSession, actor: CurrentActor
) -> RatingOut:
    """Set your rating of a work."""
    return RatingOut.model_validate(
        responses.set_rating(session, actor, work_id, payload)
    )


@router.delete(
    "/works/{work_id}/rating", operation_id="ratings_delete", status_code=_NO_CONTENT
)
def delete_rating(work_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete your rating of a work."""
    responses.delete_rating(session, actor, work_id)


@router.get("/works/{work_id}/reviews", operation_id="reviews_list")
def list_reviews(
    work_id: PathId,
    session: DbSession,
    actor: CurrentActor,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[ResponseOut]:
    """List the reviews of a work that you can see."""
    return Page[ResponseOut].model_validate(
        responses.list_reviews(session, actor, work_id, limit, offset)
    )


@router.post(
    "/works/{work_id}/reviews", operation_id="reviews_create", status_code=_CREATED
)
def create_review(
    work_id: PathId, payload: ResponseIn, session: DbSession, actor: CurrentActor
) -> ResponseOut:
    """Write a review."""
    return ResponseOut.model_validate(
        responses.create_review(session, actor, work_id, payload)
    )


@router.get("/reviews/{review_id}", operation_id="reviews_get")
def get_review(
    review_id: PathId, session: DbSession, actor: CurrentActor
) -> ResponseOut:
    """Return a review you can see."""
    return ResponseOut.model_validate(responses.get_review(session, actor, review_id))


@router.patch("/reviews/{review_id}", operation_id="reviews_update")
def update_review(
    review_id: PathId, payload: ResponsePatch, session: DbSession, actor: CurrentActor
) -> ResponseOut:
    """Change your review."""
    return ResponseOut.model_validate(
        responses.update_review(session, actor, review_id, payload)
    )


@router.delete(
    "/reviews/{review_id}", operation_id="reviews_delete", status_code=_NO_CONTENT
)
def delete_review(review_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete your review."""
    responses.delete_review(session, actor, review_id)


@router.get("/works/{work_id}/notes", operation_id="notes_list")
def list_notes(
    work_id: PathId,
    session: DbSession,
    actor: CurrentActor,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[ResponseOut]:
    """List the notes on a work that you can see."""
    return Page[ResponseOut].model_validate(
        responses.list_notes(session, actor, work_id, limit, offset)
    )


@router.post(
    "/works/{work_id}/notes", operation_id="notes_create", status_code=_CREATED
)
def create_note(
    work_id: PathId, payload: ResponseIn, session: DbSession, actor: CurrentActor
) -> ResponseOut:
    """Write a note."""
    return ResponseOut.model_validate(
        responses.create_note(session, actor, work_id, payload)
    )


@router.get("/notes/{note_id}", operation_id="notes_get")
def get_note(note_id: PathId, session: DbSession, actor: CurrentActor) -> ResponseOut:
    """Return a note you can see."""
    return ResponseOut.model_validate(responses.get_note(session, actor, note_id))


@router.patch("/notes/{note_id}", operation_id="notes_update")
def update_note(
    note_id: PathId, payload: ResponsePatch, session: DbSession, actor: CurrentActor
) -> ResponseOut:
    """Change your note."""
    return ResponseOut.model_validate(
        responses.update_note(session, actor, note_id, payload)
    )


@router.delete("/notes/{note_id}", operation_id="notes_delete", status_code=_NO_CONTENT)
def delete_note(note_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete your note."""
    responses.delete_note(session, actor, note_id)
