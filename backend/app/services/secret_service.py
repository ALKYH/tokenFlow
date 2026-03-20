from sqlalchemy import asc, select
from ..core.security import decrypt_secret, encrypt_secret
from ..models.user_secret import UserSecret


async def list_user_secrets(session, user_id: int) -> list[UserSecret]:
    result = await session.execute(
        select(UserSecret)
        .where(UserSecret.user_id == user_id)
        .order_by(asc(UserSecret.priority), asc(UserSecret.id))
    )
    return list(result.scalars().all())


async def resolve_user_secret(session, user_id: int, api_name: str | None = None) -> UserSecret | None:
    secrets = await list_user_secrets(session, user_id)
    active_secrets = [item for item in secrets if item.is_active]
    if api_name:
        normalized_name = api_name.strip().lower()
        for secret in active_secrets:
            if secret.secret_name.lower() == normalized_name or secret.provider.lower() == normalized_name:
                return secret
        return None
    return active_secrets[0] if active_secrets else None


async def upsert_user_secrets(session, user_id: int, payloads: list) -> list[UserSecret]:
    existing = await list_user_secrets(session, user_id)
    by_name = {item.secret_name.lower(): item for item in existing}
    incoming_names: set[str] = set()

    for payload in payloads:
        secret_name = payload.secret_name.strip()
        if not secret_name:
            continue

        incoming_names.add(secret_name.lower())
        secret = by_name.get(secret_name.lower())
        if not secret:
            if not payload.api_key:
                continue
            secret = UserSecret(user_id=user_id, secret_name=secret_name, encrypted_api_key=encrypt_secret(payload.api_key))
        elif payload.api_key:
            secret.encrypted_api_key = encrypt_secret(payload.api_key)

        secret.provider = (payload.provider or 'openai').strip()
        secret.secret_name = secret_name
        secret.request_prefix = (payload.request_prefix or '').strip()
        secret.priority = int(payload.priority or 100)
        secret.is_active = payload.is_active
        session.add(secret)

    for secret in existing:
        if secret.secret_name.lower() not in incoming_names:
            secret.is_active = False
            session.add(secret)

    await session.flush()
    return await list_user_secrets(session, user_id)


def mask_secret(secret: UserSecret) -> dict:
    return {
        'id': secret.id,
        'provider': secret.provider,
        'secret_name': secret.secret_name,
        'request_prefix': secret.request_prefix or '',
        'priority': secret.priority,
        'is_active': secret.is_active
    }


def build_runtime_secret(secret: UserSecret | None) -> dict:
    if not secret:
        return {}
    return {
        'provider': secret.provider,
        'api_name': secret.secret_name,
        'request_prefix': secret.request_prefix or '',
        'api_key': decrypt_secret(secret.encrypted_api_key)
    }
