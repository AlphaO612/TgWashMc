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


def pin(machine, user_id):
    redis_db.add_byNum(machine, str(user_id))

    item = main_sys.arr_washes[int(machine)]
    item.getInfo()
    return "Вы подписались!\n" + item.toString()



@dp.message(Command("status"))
async def get_statuses(message: Message):
    data_unparse = main_sys.getData()
    content = as_list(
        as_marked_section(
            Bold("ВСЕ стиралки:"),
            *[item.toString(date=False) for item in data_unparse],
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
async def cmd_alert(message: types.Message):
    data = []
    for i in range(6):
        data.append(str(message.from_user.id) in redis_db.get_byNum(i))

    await message.answer("*Вы подписались на 🔔оповещение🔔:*  \n 🔹 " +\
                         ("\n 🔹 ".join([f'№{i+1} стирка' for i, item in enumerate(data) if item]) if sum(data) else "Пусто"),
                         parse_mode=parse_mode.ParseMode.MARKDOWN_V2)


@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    data = []
    for i in range(6):
        data.append(str(message.from_user.id) in redis_db.get_byNum(i))
        if str(message.from_user.id) in redis_db.get_byNum(i):
            redis_db.remove_byNum(i,str(message.from_user.id))

    await message.answer("*Вы ОТПИСАЛИСЬ от 🔕оповещений🔕:*  \n 🔹 " +\
                         ("\n 🔹 ".join([f'№{i+1} стирка' for i, item in enumerate(data) if item]) if sum(data) else "Пусто"),
                         parse_mode=parse_mode.ParseMode.MARKDOWN_V2)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
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
async def send_random_value(callback: types.CallbackQuery):
    text = pin(*list(map(int, callback.data.split("_"))))
    await callback.message.answer(text)
    await callback.answer(
        text=text,
        show_alert=True
    )

@dp.message(Command("setalert"))
async def cmd_setalert(
        message: Message,
        command: CommandObject
):
    # Если не переданы никакие аргументы, то
    # command.args будет None
    if command.args is None:
        await message.answer(
            "Ошибка: не переданы аргументы"
        )
        return
    # Пробуем разделить аргументы на две части по первому встречному пробелу
    try:
        machine = int(command.args.split(" ", maxsplit=1)[0])
        if not 0 < machine < 7:
            raise ValueError("User wrong value!")
    # Если получилось меньше двух частей, вылетит ValueError
    except ValueError:
        await message.answer(
            "Ошибка: неправильный формат команды. Пример:\n"
            "/setalarm <number-wash-machine>"
        )
        return

    text = pin(machine-1, message.from_user.id)
    await message.answer(
        text
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
