import asyncio, logging, Usys, redis, settings
import json
from enum import Enum

from aiogram import Bot, Dispatcher, types, F
from aiogram.dispatcher import router
from aiogram.enums import parse_mode
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.types import Message, CallbackQuery
from aiogram.utils.formatting import (
    Bold, Italic, as_list, as_marked_section, as_key_value, HashTag
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from logger import setup_logger, log_function

# Create logger for main
logger = setup_logger('main')

# Включаем логирование, чтобы не пропустить важные сообщения
logging.basicConfig(level=logging.INFO)
# Объект бота
bot = Bot(token=settings.BOT_TOKEN)
main_sys = Usys.UniMeter(redis.StrictRedis(
    **settings.REDIS_DB
))
# Диспетчер
dp = Dispatcher()
redis_db = Usys.RedisUser(redis.StrictRedis(
    **settings.REDIS_DB
))

class AdminAction(CallbackData, prefix="adm"):
    user_id: int
    wash_id: int

@log_function(logger)
def pin(machine, user_id):
    logger.info(f"User {user_id} subscribing to machine #{machine}")
    redis_db.add_by_num(machine, str(user_id))
    item = main_sys.arr_washes[int(machine)]
    item.get_info()
    return "Вы подписались!\n" + item.to_string()

@dp.message(Command("status"))
@log_function(logger)
async def get_statuses(message: Message):
    logger.info(f"Status requested by user {message.from_user.id}")
    data_unparse = main_sys.getData()
    content = as_list(
        as_marked_section(
            Bold("ВСЕ стиралки:"),
            *[item.to_string(date=False) for item in data_unparse],
            marker="  ",
        ),
        Italic("Можете подписаться на изменение к стиралке:"),
        sep="\n\n",
    )
    builder = InlineKeyboardBuilder()
    for i in range(6):
        builder.button(
            text=f"№{i+1}",
            callback_data="{wash_id}_{user_id}".format(wash_id=i, user_id=message.from_user.id)
        )
    await message.answer(**content.as_kwargs(), reply_markup=builder.as_markup())

@dp.message(Command("alert"))
@log_function(logger)
async def cmd_alert(message: types.Message):
    logger.info(f"Alert subscriptions requested by user {message.from_user.id}")
    data = []
    for i in range(6):
        data.append(str(message.from_user.id) in redis_db.get_by_num(i))

    await message.answer("*Вы подписались на 🔔оповещение🔔:*  \n 🔹 " +\
                         ("\n 🔹 ".join([f'№{i+1} стирка' for i, item in enumerate(data) if item]) if sum(data) else "Пусто"),
                         parse_mode=parse_mode.ParseMode.MARKDOWN_V2)

@dp.message(Command("clear"))
@log_function(logger)
async def cmd_clear(message: types.Message):
    logger.info(f"Clear subscriptions requested by user {message.from_user.id}")
    data = []
    for i in range(6):
        data.append(str(message.from_user.id) in redis_db.get_by_num(i))
        if str(message.from_user.id) in redis_db.get_by_num(i):
            redis_db.remove_by_num(i,str(message.from_user.id))

    await message.answer("*Вы ОТПИСАЛИСЬ от 🔕оповещений🔕:*  \n 🔹 " +\
                         ("\n 🔹 ".join([f'№{i+1} стирка' for i, item in enumerate(data) if item]) if sum(data) else "Пусто"),
                         parse_mode=parse_mode.ParseMode.MARKDOWN_V2)

@dp.message(Command("start"))
@log_function(logger)
async def cmd_start(message: types.Message):
    logger.info(f"Start command received from user {message.from_user.id}")
    try:
        redis_db.add_user_data(str(message.from_user.id) + "_" + message.from_user.full_name)
    finally:
        pass
    data = {
        "start": ("Информация по боту\. Список команд\.", "🔰Информация"),
        "status":("Список статусов стиралок", "🌐Статусы стиралок"),
        "setalert \<number\>":(
            "Подписка единоразовая на получение изменения статуса\. То есть если стиралка достирала, "
            "то вы получите сообщение об этом и подписка исчезнет\!",
            ""),
        "alert":("Список на какие машинки вы подписаны", "🔔Подписанные машинки"),
        "clear":("Удаление всех подписок", "❌Удалить подписки"),
    }

    kb = [
        [types.KeyboardButton(text=f"/{i} - {data[i][1]}")] for i in data if "setalert" not in i
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb)
    await message.answer("Приветики\! \n _Бот напомнит вам, что ваша машинка достиралась\! или что она наконец освободилось"
                         " и можно идти забирать вещи\._\n Написал [@arefaste]()"
                         "\n*Команды:*"
                         "\n 🔹 "+"\n 🔹 ".join([f'/{item} \- {data[item][0]}' for item in data])+\
                         "\n\n", parse_mode=parse_mode.ParseMode.MARKDOWN_V2,
                         reply_markup=keyboard)

@dp.callback_query()
@log_function(logger)
async def send_random_value(callback: types.CallbackQuery):
    logger.info(f"Callback query received from user {callback.from_user.id}")
    text = pin(*list(map(int, callback.data.split("_"))))
    await callback.message.answer(text)
    await callback.answer(
        text=text,
        show_alert=True
    )

@dp.message(Command("setalert"))
@log_function(logger)
async def cmd_setalert(
        message: Message,
        command: CommandObject
):
    logger.info(f"Setalert command received from user {message.from_user.id}")
    if command.args is None:
        logger.warning(f"Setalert command received without arguments from user {message.from_user.id}")
        await message.answer(
            "Ошибка: не переданы аргументы"
        )
        return
    try:
        machine = int(command.args.split(" ", maxsplit=1)[0])
        if not 0 < machine < 7:
            raise ValueError("User wrong value!")
    except ValueError:
        logger.error(f"Invalid machine number provided by user {message.from_user.id}: {command.args}")
        await message.answer(
            "Ошибка: неправильный формат команды. Пример:\n"
            "/setalarm <number-wash-machine>"
        )
        return

    text = pin(machine-1, message.from_user.id)
    await message.answer(
        text
    )

@dp.message(Command("subscribers"))
@log_function(logger)
async def cmd_subscribers(message: Message):
    """Admin-only command to view subscribers for each washing machine"""
    # Check if user is admin
    if message.from_user.id != settings.ADMIN_ID:
        logger.info(f"Unauthorized subscriber list request from user {message.from_user.id}")
        return
    
    logger.info(f"Subscriber list requested by admin {message.from_user.id}")
    
    # Get subscribers for each machine
    subscriber_data = []
    for i in range(6):
        users = redis_db.get_by_num(i)
        subscriber_data.append({
            "machine_num": i+1,
            "user_count": len(users),
            "users": users
        })
    
    # Format response
    content = as_list(
        Bold("📊 WASHING MACHINE SUBSCRIBERS 📊"),
        *[f"Machine #{item['machine_num']}: {item['user_count']} subscribers" for item in subscriber_data],
        sep="\n",
    )
    
    # Add detailed view option
    builder = InlineKeyboardBuilder()
    for i in range(6):
        if subscriber_data[i]['user_count'] > 0:
            builder.button(
                text=f"Details for #{i+1}",
                callback_data=AdminAction(user_id=message.from_user.id, wash_id=i).pack()
            )
    
    await message.answer(**content.as_kwargs(), reply_markup=builder.as_markup())

# Add handler for the admin callback
@dp.callback_query(AdminAction.filter())
@log_function(logger)
async def show_subscriber_details(callback: CallbackQuery, callback_data: AdminAction):
    # Verify admin permission again
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("Unauthorized access")
        return
    
    wash_id = callback_data.wash_id
    users = redis_db.get_by_num(wash_id)
    
    if not users:
        await callback.answer(f"No subscribers for machine #{wash_id+1}")
        return
    
    text = f"📋 Subscribers for machine #{wash_id+1}:\n"
    for i, user_id in enumerate(users, 1):
        text += f"{i}. User ID: {user_id}\n"
    
    await callback.message.answer(text)
    await callback.answer()

async def main():
    logger.info("Starting main bot loop")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
