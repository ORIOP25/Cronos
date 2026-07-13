import redis

from app.config import settings


def latest_schedule_cache_key(organization_id: int) -> str:
    return f"schedule_latest_data_{organization_id}"


def invalidate_latest_schedule_cache(organization_id: int) -> None:
    client = redis.Redis.from_url(
        str(settings.REDIS_URL),
        decode_responses=True,
        socket_connect_timeout=2,
    )
    try:
        client.delete(latest_schedule_cache_key(organization_id))
    finally:
        client.close()
