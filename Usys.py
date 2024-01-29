import requests, datetime, time, redis, json

from bs4 import BeautifulSoup
from typing import Optional

import settings


class WashMach:

    format_dt = "%d.%m.%Y в %H:%M"
    class heheRedis:
        def __init__(self, redis_db: redis.StrictRedis):
            self.redis_db = redis_db
            self.filler_data()

        @property
        def name_db(self):
            return 'wash_data'

        def filler_data(self):
            clear_db = lambda: self.redis_db.lpush(self.name_db, *sorted([
                json.dumps(
                    dict(
                        num=i,
                        status=False,
                        upd_dt=datetime.datetime.now().strftime("%d.%m.%Y в %H:%M")
                    ),
                    ensure_ascii=True,
                    indent=4
                ) for i in range(1,7)
            ], reverse=True))
            if not self.redis_db.exists(self.name_db): clear_db()

        def get_byNum(self, num: int):
            return json.loads(self.redis_db.lindex(self.name_db, num-1))

        def write_byNum(self, num: int, data: dict):
            self.redis_db.lset(self.name_db, num-1, json.dumps(data, ensure_ascii=True, indent=4))

    def __init__(self, num: int, status: bool, upd_dt: str = "26.01.2024 в 14:49", redis_db: Optional[redis.StrictRedis] = None):
        self.num: int = num
        self.status: bool = status
        self.upd_dt: datetime.datetime = datetime.datetime.strptime(upd_dt, self.format_dt)
        self.alert_func = lambda num, status, old_status, upd_dt, old_upd_dt: print(f"№{num} wash Mach — {'Занято' if status else 'СВОБОДНО'}")
        self._redis = redis_db
        if redis_db:
            self._redis = self.heheRedis(redis_db)

    def compare(self, num: int, status: bool, upd_dt: str):
        dt = self.upd_dt.timestamp()
        if abs(datetime.datetime.strptime(upd_dt, self.format_dt).timestamp() - dt) > 0 and self.num == num:
            old_status = self.status
            self.status: bool = status
            if old_status != status:
                old_upd_dt = self.upd_dt
                self.upd_dt: datetime.datetime = datetime.datetime.strptime(upd_dt, self.format_dt)
                if self._redis:
                    self._redis.write_byNum(num, self.getInfo(FromRedis=False))
                self.alert_func(num, status, old_status, upd_dt, old_upd_dt)

    def _fill_from_db(self):
        if self._redis:
            data = self._redis.get_byNum(self.num)
            self.status: bool = data['status']
            self.upd_dt: datetime.datetime = datetime.datetime.strptime(data['upd_dt'], self.format_dt)

    def getInfo(self, FromRedis: bool = True):
        if FromRedis:
            self._fill_from_db()
        return dict(
            num=self.num,
            status=self.status,
            upd_dt=self.upd_dt.strftime(self.format_dt)
        )

    def toString(self, date=True):
        return f'🧻№{self.num}  - {"‼️BUSY‼️" if self.status else "✅Free"}' + (f'\nДата обновления: {self.upd_dt}' if date else "")


class UniMeter:
    def __init__(self, redis_db: Optional[redis.StrictRedis] = None, server_mode: bool = False):
        self._server_mode = server_mode
        self.ses = requests.Session()
        self.headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        self._redis = redis_db
        self.arr_washes: list[WashMach] = [WashMach(i, False, redis_db=self._redis) for i in range(1, 7)]
        self.getData()

    def getData(self):
        if not self._redis or self._server_mode:
            undata = BeautifulSoup(self.ses.get("https://cabinet.unimetriq.com/client/6703b4b333805792cfa639770058bd45",
                                                headers=self.headers).content, "html.parser")
            for i, data_wash in enumerate(undata.findAll("div", {"title": "СТИРКА"})):
                arr_divs = data_wash.findAll("div")[1:]
                if self._redis:
                    self.arr_washes[i].getInfo()
                self.arr_washes[i].compare(
                    num=int(arr_divs[0].text),
                    status= True if "анято" in arr_divs[-1].text.strip().strip("\n") else False,
                    upd_dt=undata.find("div", {"data-toggle":"tooltip"})['title'].replace("Последний обмен данными ", "")
                )
                time.sleep(1)
            return self.arr_washes
        else:
            for i, data_wash in enumerate(self.arr_washes):
                data_wash.getInfo()
            return self.arr_washes


class RedisUser:
    def __init__(self, redis_db: redis.StrictRedis):
        self.redis_db = redis_db

    def name_db(self, num: int):
        return f'wash_alarmer:{num}'

    def clear_byNum(self, num: int):
        self.redis_db.delete(self.name_db(num))

    def add_byNum(self, num: int, user_id: str):
        self.redis_db.sadd(self.name_db(num), user_id)

    def remove_byNum(self, num: int, user_id: str):
        self.redis_db.srem(self.name_db(num), user_id)

    def get_byNum(self, num: int):
        data = self.redis_db.smembers(self.name_db(num))

        return list(map(lambda x: x.decode("utf-8"), list(data)))

    def pop_byNum(self, num: int):
        while True:
            popped_element = self.redis_db.spop(self.name_db(num))
            if popped_element is None:
                break
            yield popped_element.decode("utf-8")