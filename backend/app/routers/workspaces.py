from sqlalchemy import desc, select
from fastapi import APIRouter, Depends
from ..deps import get_current_user, get_session
from ..models.workspace_file import WorkspaceFile
from ..schemas.workspace import WorkspaceFileCreate, WorkspaceFileRead

router = APIRouter(prefix='/api/workspaces', tags=['workspaces'])


@router.get('', response_model=list[WorkspaceFileRead])
async def list_workspaces(session=Depends(get_session), user=Depends(get_current_user)):
    stmt = select(WorkspaceFile).where(WorkspaceFile.owner_id == user.id).order_by(desc(WorkspaceFile.updated_at))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post('', response_model=WorkspaceFileRead)
async def save_workspace(payload: WorkspaceFileCreate, session=Depends(get_session), user=Depends(get_current_user)):
    workspace = WorkspaceFile(
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        file_type=payload.file_type,
        content=payload.content
    )
    session.add(workspace)
    await session.commit()
    await session.refresh(workspace)
    return workspace
