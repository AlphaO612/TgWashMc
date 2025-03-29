import asyncio, logging, Usys, redis, settings
import time

import requests
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.formatting import (
    Bold, as_list, as_marked_section, as_key_value, HashTag
)
from logger import setup_logger, log_function

USER_ID = settings.ADMIN_ID
main_sys = Usys.UniMeter(redis_db=redis.StrictRedis(**settings.REDIS_DB), server_mode=True)

redis_db = Usys.RedisUser(redis_db=redis.StrictRedis(**settings.REDIS_DB))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()

# Создаем logger для redis_parser
logger = setup_logger('redis_parser')

@dp.startup()
@log_function(logger)
async def on_startup(*args, **kwargs):
    logger.info("Bot starting up...")
    await bot.send_message(USER_ID, "bot started!<3")
    while True:
        logger.info("Fetching washing machine data...")
        main_sys.getData()
        time.sleep(10)


@dp.message(Command("admin_stat"))
@log_function(logger)
async def cmd_start(message: types.Message):
    logger.info(f"Admin stats requested by user {message.from_user.id}")
    await message.answer("Приветики! \n ")


def send_message(chat_id, text, token=settings.BOT_TOKEN):
    base_url = f"https://api.telegram.org/bot{token}/sendMessage"
    params = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'markdown'
    }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        logger.info(f"Message sent successfully to chat {chat_id}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending message to chat {chat_id}: {e}")

@log_function(logger)
def react(num, status, old_status, upd_dt, old_upd_dt):
    logger.info(f"Reacting to status change for machine #{num}: {old_status} -> {status}")
    for data in redis_db.pop_by_num(num-1):
        send_message(data, f"*🔔 - 🧻№{num} Изменилась*\n"
                     f'🧻№{num}  - *{"‼️BUSY‼️" if old_status else "✅Free"}* изменился на *{"‼️BUSY‼️" if status else "✅Free"}*\n\t'
                     f'\nДата обновления: {upd_dt}')



async def main():
    logger.info("Starting redis_parser main loop")
    await dp.start_polling(bot)

if __name__ == '__main__':
    logger.info("Setting up alert functions for all washing machines")
    for item in main_sys.arr_washes:
        item.alert_func = react
    asyncio.run(main())
