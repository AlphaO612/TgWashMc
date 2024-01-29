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

USER_ID = settings.ADMIN_ID
main_sys = Usys.UniMeter(redis_db=redis.StrictRedis(**settings.REDIS_DB), server_mode=True)

redis_db = Usys.RedisUser(redis_db=redis.StrictRedis(**settings.REDIS_DB))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()

@dp.startup()
async def on_startup(*args, **kwargs):
    while True:
        main_sys.getData()
        time.sleep(2)


@dp.message(Command("admin_stat"))
async def cmd_start(message: types.Message):
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
        print("Message sent successfully!")
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")
def react(num, status, old_status, upd_dt, old_upd_dt):
    for data in redis_db.pop_byNum(num-1):
        send_message(data, f"*🔔 - 🧻№{num} Изменилась*\n"
                     f'🧻№{num}  - *{"‼️BUSY‼️" if old_status else "✅Free"}* изменился на *{"‼️BUSY‼️" if status else "✅Free"}*\n\t'
                     f'\nДата обновления: {upd_dt}')



async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    for item in main_sys.arr_washes:
        item.alert_func = react
    asyncio.run(main())
