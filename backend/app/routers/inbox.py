from sqlalchemy import desc, or_, select
from fastapi import APIRouter, Depends
from ..deps import get_optional_user, get_session
from ..models.inbox_message import InboxMessage
from ..schemas.inbox import InboxMessageRead

router = APIRouter(prefix='/api/inbox', tags=['inbox'])


@router.get('/messages', response_model=list[InboxMessageRead])
async def get_messages(session=Depends(get_session), user=Depends(get_optional_user)):
    stmt = select(InboxMessage).where(InboxMessage.owner_id.is_(None))
    if user:
        stmt = select(InboxMessage).where(or_(InboxMessage.owner_id.is_(None), InboxMessage.owner_id == user.id))
    result = await session.execute(stmt.order_by(desc(InboxMessage.created_at)))
    return list(result.scalars().all())
