from sqlalchemy import case, desc, func, or_, select
from fastapi import APIRouter, Depends, Query
from ..deps import get_optional_user, get_session
from ..models.inbox_message import InboxMessage
from ..schemas.inbox import InboxChannelSummary, InboxMessageCreate, InboxMessageRead, InboxMessageReadUpdate

router = APIRouter(prefix='/api/inbox', tags=['inbox'])


@router.get('/messages', response_model=list[InboxMessageRead])
async def get_messages(
    channel: str | None = Query(default=None),
    category: str | None = Query(default=None),
    session=Depends(get_session),
    user=Depends(get_optional_user)
):
    stmt = select(InboxMessage).where(InboxMessage.owner_id.is_(None))
    if user:
        stmt = select(InboxMessage).where(or_(InboxMessage.owner_id.is_(None), InboxMessage.owner_id == user.id))
    if channel and channel != 'all':
        stmt = stmt.where(InboxMessage.channel == channel)
    if category and category != 'all':
        stmt = stmt.where(InboxMessage.category == category)
    result = await session.execute(stmt.order_by(desc(InboxMessage.created_at)))
    return list(result.scalars().all())


@router.get('/channels', response_model=list[InboxChannelSummary])
async def get_message_channels(session=Depends(get_session), user=Depends(get_optional_user)):
    stmt = select(
        InboxMessage.channel,
        func.count(InboxMessage.id),
        func.sum(case((InboxMessage.is_read.is_(False), 1), else_=0))
    ).group_by(InboxMessage.channel)
    if user:
        stmt = stmt.where(or_(InboxMessage.owner_id.is_(None), InboxMessage.owner_id == user.id))
    else:
        stmt = stmt.where(InboxMessage.owner_id.is_(None))
    result = await session.execute(stmt.order_by(InboxMessage.channel.asc()))
    return [
        InboxChannelSummary(channel=channel, count=count or 0, unread=unread or 0)
        for channel, count, unread in result.all()
    ]


@router.post('/messages', response_model=InboxMessageRead)
async def create_message(payload: InboxMessageCreate, session=Depends(get_session), user=Depends(get_optional_user)):
    message = InboxMessage(
        owner_id=user.id if user else None,
        title=payload.title,
        body=payload.body,
        category=payload.category,
        channel=payload.channel,
        source=payload.source,
        attachments=payload.attachments,
        extra=payload.extra
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


@router.post('/ingest', response_model=InboxMessageRead)
async def ingest_message(payload: InboxMessageCreate, session=Depends(get_session), user=Depends(get_optional_user)):
    return await create_message(payload, session=session, user=user)


@router.patch('/messages/read', response_model=list[InboxMessageRead])
async def mark_messages_read(payload: InboxMessageReadUpdate, session=Depends(get_session), user=Depends(get_optional_user)):
    stmt = select(InboxMessage).where(InboxMessage.id.in_(payload.ids))
    if user:
        stmt = stmt.where(or_(InboxMessage.owner_id.is_(None), InboxMessage.owner_id == user.id))
    else:
        stmt = stmt.where(InboxMessage.owner_id.is_(None))
    result = await session.execute(stmt)
    items = list(result.scalars().all())
    for item in items:
        item.is_read = payload.is_read
        session.add(item)
    await session.commit()
    for item in items:
        await session.refresh(item)
    return items
