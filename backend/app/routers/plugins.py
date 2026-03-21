from sqlalchemy import desc, or_, select
from fastapi import APIRouter, Depends, HTTPException, Query
from ..deps import get_current_user, get_optional_user, get_session
from ..models.plugin import Plugin
from ..models.workspace_file import WorkspaceFile
from ..schemas.plugin import PluginCreate, PluginInstallResponse, PluginPublishFromWorkspace, PluginRead
from ..schemas.routing import RoutingResolveRequest
from ..services.secret_service import build_runtime_secret, resolve_user_secret
from .routing import _resolve_category_and_channel

router = APIRouter(prefix='/api/plugins', tags=['plugins'])


@router.get('/marketplace', response_model=list[PluginRead])
async def list_marketplace_plugins(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    plugin_type: str | None = Query(default=None),
    session=Depends(get_session)
):
    stmt = select(Plugin).where(Plugin.is_public.is_(True))
    if q:
      like = f'%{q.strip()}%'
      stmt = stmt.where(or_(Plugin.name.ilike(like), Plugin.summary.ilike(like), Plugin.author_name.ilike(like)))
    if category and category != 'all':
      stmt = stmt.where(Plugin.category == category)
    if plugin_type and plugin_type != 'all':
      stmt = stmt.where(Plugin.plugin_type == plugin_type)
    result = await session.execute(stmt.order_by(desc(Plugin.installs), desc(Plugin.updated_at)))
    return list(result.scalars().all())


@router.get('/library', response_model=list[PluginRead])
async def list_my_plugins(
    plugin_type: str | None = Query(default=None),
    library_kind: str | None = Query(default=None),
    session=Depends(get_session),
    user=Depends(get_current_user)
):
    stmt = select(Plugin).where(Plugin.owner_id == user.id)
    if plugin_type and plugin_type != 'all':
        stmt = stmt.where(Plugin.plugin_type == plugin_type)
    if library_kind and library_kind != 'all':
        stmt = stmt.where(Plugin.library_kind == library_kind)
    stmt = stmt.order_by(desc(Plugin.updated_at))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post('/upload', response_model=PluginRead)
async def upload_plugin(payload: PluginCreate, session=Depends(get_session), user=Depends(get_current_user)):
    existing = await session.execute(select(Plugin).where(Plugin.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail='Plugin slug already exists')
    plugin = Plugin(
        owner_id=user.id,
        name=payload.name,
        slug=payload.slug,
        summary=payload.summary,
        category=payload.category,
        plugin_type=payload.plugin_type,
        author_name=payload.author_name or user.display_name,
        icon=payload.icon,
        tags=payload.tags,
        source=payload.source,
        route_info=payload.route_info,
        library_kind=payload.library_kind,
        workspace_snapshot=payload.workspace_snapshot,
        node_template_snapshot=payload.node_template_snapshot,
        is_public=payload.is_public
    )
    session.add(plugin)
    await session.commit()
    await session.refresh(plugin)
    return plugin


@router.post('/publish-workspace', response_model=PluginRead)
async def publish_workspace_as_plugin(payload: PluginPublishFromWorkspace, session=Depends(get_session), user=Depends(get_current_user)):
    workspace = None
    if payload.workspace_id is not None:
        workspace = await session.get(WorkspaceFile, payload.workspace_id)
        if not workspace or workspace.owner_id != user.id:
            raise HTTPException(status_code=404, detail='Workspace not found')

    runtime_secret = build_runtime_secret(await resolve_user_secret(session, user.id, payload.request_api_name))
    resolved_category, resolved_channel, route_kind = _resolve_category_and_channel(
        RoutingResolveRequest(
            category=payload.category,
            channel=None,
            api_name=payload.request_api_name,
            file_name=workspace.name if workspace else payload.name,
            file_type=payload.file_type or (workspace.file_type if workspace else 'workspace')
        ),
        runtime_secret
    )

    plugin = Plugin(
        owner_id=user.id,
        name=payload.name,
        slug=payload.slug,
        summary=payload.summary,
        category=resolved_category,
        plugin_type=payload.plugin_type,
        author_name=user.display_name,
        icon=payload.icon,
        tags=payload.tags,
        source={
            'channel': 'workspace-publish',
            'workspace_id': workspace.id if workspace else None,
            'file_type': payload.file_type or (workspace.file_type if workspace else 'workspace'),
            'request_api_name': payload.request_api_name
        },
        route_info={
            'category': resolved_category,
            'channel': resolved_channel,
            'route_kind': route_kind,
            'selected_api': {k: v for k, v in runtime_secret.items() if k != 'api_key'}
        },
        library_kind=payload.library_kind,
        workspace_snapshot=workspace.content if workspace else None,
        is_public=payload.is_public
    )
    session.add(plugin)
    await session.commit()
    await session.refresh(plugin)
    return plugin


@router.post('/install/{plugin_id}', response_model=PluginInstallResponse)
async def install_plugin(plugin_id: int, session=Depends(get_session), _user=Depends(get_optional_user)):
    plugin = await session.get(Plugin, plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')
    plugin.installs += 1
    plugin.downloads += 1
    session.add(plugin)
    await session.commit()
    await session.refresh(plugin)
    return {'installed': True, 'plugin': plugin}
