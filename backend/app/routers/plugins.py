from sqlalchemy import desc, or_, select
from fastapi import APIRouter, Depends, HTTPException, Query
from ..deps import get_current_user, get_optional_user, get_session
from ..models.plugin import Plugin
from ..schemas.plugin import PluginCreate, PluginInstallResponse, PluginRead

router = APIRouter(prefix='/api/plugins', tags=['plugins'])


@router.get('/marketplace', response_model=list[PluginRead])
async def list_marketplace_plugins(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    session=Depends(get_session)
):
    stmt = select(Plugin).where(Plugin.is_public.is_(True))
    if q:
      like = f'%{q.strip()}%'
      stmt = stmt.where(or_(Plugin.name.ilike(like), Plugin.summary.ilike(like), Plugin.author_name.ilike(like)))
    if category and category != 'all':
      stmt = stmt.where(Plugin.category == category)
    result = await session.execute(stmt.order_by(desc(Plugin.installs), desc(Plugin.updated_at)))
    return list(result.scalars().all())


@router.get('/library', response_model=list[PluginRead])
async def list_my_plugins(session=Depends(get_session), user=Depends(get_current_user)):
    stmt = select(Plugin).where(Plugin.owner_id == user.id).order_by(desc(Plugin.updated_at))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post('/upload', response_model=PluginRead)
async def upload_plugin(payload: PluginCreate, session=Depends(get_session), user=Depends(get_current_user)):
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
        workspace_snapshot=payload.workspace_snapshot,
        node_template_snapshot=payload.node_template_snapshot,
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
