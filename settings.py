import os
REDIS_DB: dict = dict(
        host="redis.arefaste",
        port=6379,
        db=0,
        password=None,
)

BOT_TOKEN: str = os.getenv("bot_token")

ADMIN_ID: int = 504467583