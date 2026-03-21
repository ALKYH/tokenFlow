from sqlalchemy import desc, select
from fastapi import APIRouter, Depends, HTTPException, Query
from ..deps import get_current_user, get_session
from ..models.workspace_file import WorkspaceFile
from ..schemas.workspace import WorkspaceFileCreate, WorkspaceFileRead

router = APIRouter(prefix='/api/workspaces', tags=['workspaces'])


@router.get('', response_model=list[WorkspaceFileRead])
async def list_workspaces(
    file_type: str | None = Query(default=None),
    session=Depends(get_session),
    user=Depends(get_current_user)
):
    stmt = select(WorkspaceFile).where(WorkspaceFile.owner_id == user.id)
    if file_type and file_type != 'all':
        stmt = stmt.where(WorkspaceFile.file_type == file_type)
    stmt = stmt.order_by(desc(WorkspaceFile.updated_at))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get('/{workspace_id}', response_model=WorkspaceFileRead)
async def get_workspace(workspace_id: int, session=Depends(get_session), user=Depends(get_current_user)):
    workspace = await session.get(WorkspaceFile, workspace_id)
    if not workspace or workspace.owner_id != user.id:
        raise HTTPException(status_code=404, detail='Workspace not found')
    return workspace


@router.post('', response_model=WorkspaceFileRead)
async def save_workspace(payload: WorkspaceFileCreate, session=Depends(get_session), user=Depends(get_current_user)):
    workspace = None
    if payload.id is not None:
        workspace = await session.get(WorkspaceFile, payload.id)
        if workspace and workspace.owner_id != user.id:
            raise HTTPException(status_code=404, detail='Workspace not found')
    if workspace is None:
        workspace = WorkspaceFile(
            owner_id=user.id,
            name=payload.name,
            description=payload.description,
            file_type=payload.file_type,
            content=payload.content
        )
    else:
        workspace.name = payload.name
        workspace.description = payload.description
        workspace.file_type = payload.file_type
        workspace.content = payload.content
    session.add(workspace)
    await session.commit()
    await session.refresh(workspace)
    return workspace
