"""Groups: users and libraries that share with each other."""

from fastapi import APIRouter, status

from librelibrary.api.deps import CurrentActor, DbSession, Limit, Offset, PathId
from librelibrary.schemas import (
    GroupIn,
    GroupLibraryOut,
    GroupMemberOut,
    GroupOut,
    Page,
)
from librelibrary.services import groups

router = APIRouter(tags=["groups"])
_NO_CONTENT = status.HTTP_204_NO_CONTENT


@router.get("/groups", operation_id="groups_list")
def list_groups(
    session: DbSession, actor: CurrentActor, limit: Limit = 50, offset: Offset = 0
) -> Page[GroupOut]:
    """List the groups you belong to."""
    return Page[GroupOut].model_validate(
        groups.list_groups(session, actor, limit, offset)
    )


@router.get("/groups/all", operation_id="groups_list_all")
def list_all_groups(
    session: DbSession, actor: CurrentActor, limit: Limit = 50, offset: Offset = 0
) -> Page[GroupOut]:
    """List every group. Needs the admin scope."""
    return Page[GroupOut].model_validate(
        groups.list_all_groups(session, actor, limit, offset)
    )


@router.post(
    "/groups", operation_id="groups_create", status_code=status.HTTP_201_CREATED
)
def create_group(payload: GroupIn, session: DbSession, actor: CurrentActor) -> GroupOut:
    """Create a group. Needs the admin scope."""
    return GroupOut.model_validate(groups.create_group(session, actor, payload))


@router.get("/groups/{group_id}", operation_id="groups_get")
def get_group(group_id: PathId, session: DbSession, actor: CurrentActor) -> GroupOut:
    """Return a group you belong to."""
    return GroupOut.model_validate(groups.get_group(session, actor, group_id))


@router.patch("/groups/{group_id}", operation_id="groups_update")
def update_group(
    group_id: PathId, payload: GroupIn, session: DbSession, actor: CurrentActor
) -> GroupOut:
    """Rename a group. Needs the admin scope."""
    return GroupOut.model_validate(
        groups.update_group(session, actor, group_id, payload)
    )


@router.delete(
    "/groups/{group_id}", operation_id="groups_delete", status_code=_NO_CONTENT
)
def delete_group(group_id: PathId, session: DbSession, actor: CurrentActor) -> None:
    """Delete a group. Needs the admin scope."""
    groups.delete_group(session, actor, group_id)


@router.get("/groups/{group_id}/members", operation_id="group_members_list")
def list_members(
    group_id: PathId,
    session: DbSession,
    actor: CurrentActor,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[GroupMemberOut]:
    """List a group's members."""
    return Page[GroupMemberOut].model_validate(
        groups.list_members(session, actor, group_id, limit, offset)
    )


@router.put(
    "/groups/{group_id}/members/{user_id}",
    operation_id="group_members_add",
    status_code=_NO_CONTENT,
)
def add_member(
    group_id: PathId, user_id: PathId, session: DbSession, actor: CurrentActor
) -> None:
    """Add a user to a group. Needs the admin scope."""
    groups.add_member(session, actor, group_id, user_id)


@router.delete(
    "/groups/{group_id}/members/{user_id}",
    operation_id="group_members_remove",
    status_code=_NO_CONTENT,
)
def remove_member(
    group_id: PathId, user_id: PathId, session: DbSession, actor: CurrentActor
) -> None:
    """Remove a user from a group. Needs the admin scope."""
    groups.remove_member(session, actor, group_id, user_id)


@router.get("/groups/{group_id}/libraries", operation_id="group_libraries_list")
def list_libraries(
    group_id: PathId,
    session: DbSession,
    actor: CurrentActor,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[GroupLibraryOut]:
    """List the libraries in a group."""
    return Page[GroupLibraryOut].model_validate(
        groups.list_libraries(session, actor, group_id, limit, offset)
    )


@router.put(
    "/groups/{group_id}/libraries/{library_id}",
    operation_id="group_libraries_add",
    status_code=_NO_CONTENT,
)
def add_library(
    group_id: PathId, library_id: PathId, session: DbSession, actor: CurrentActor
) -> None:
    """Add a library you own to a group you belong to."""
    groups.add_library(session, actor, group_id, library_id)


@router.delete(
    "/groups/{group_id}/libraries/{library_id}",
    operation_id="group_libraries_remove",
    status_code=_NO_CONTENT,
)
def remove_library(
    group_id: PathId, library_id: PathId, session: DbSession, actor: CurrentActor
) -> None:
    """Take a library out of a group. Its owner or an admin can do this."""
    groups.remove_library(session, actor, group_id, library_id)
