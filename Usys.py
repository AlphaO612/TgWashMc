import requests, datetime, time, redis, json

from bs4 import BeautifulSoup
from typing import Optional, Dict, List, Callable, Any, Union

import settings
from logger import setup_logger, log_function

# Create logger for Usys
logger = setup_logger('Usys')


class WashMachRedis:
    """Class for handling washing machine data in Redis."""
    
    def __init__(self, redis_db: redis.StrictRedis):
        self.redis_db = redis_db
        self.initialize_data()

    @property
    def name_db(self) -> str:
        return 'wash_data'

    @log_function(logger)
    def initialize_data(self) -> None:
        """Initialize Redis with default washing machine data if it doesn't exist."""
        if not self.redis_db.exists(self.name_db):
            initial_data = [
                json.dumps(
                    dict(
                        num=i,
                        status=False,
                        upd_dt=datetime.datetime.now().strftime("%d.%m.%Y в %H:%M")
                    ),
                    ensure_ascii=True,
                    indent=4
                ) for i in range(1, 7)
            ]
            # Add data in reverse order to maintain correct indexing
            self.redis_db.lpush(self.name_db, *sorted(initial_data, reverse=True))

    @log_function(logger)
    def get_by_num(self, num: int) -> Dict[str, Any]:
        """Get washing machine data by number."""
        return json.loads(self.redis_db.lindex(self.name_db, num-1))

    @log_function(logger)
    def write_by_num(self, num: int, data: Dict[str, Any]) -> None:
        """Update washing machine data by number."""
        self.redis_db.lset(self.name_db, num-1, json.dumps(data, ensure_ascii=True, indent=4))


class WashMach:
    """Class representing a washing machine."""
    
    FORMAT_DT = "%d.%m.%Y в %H:%M"
    
    def __init__(self, num: int, status: bool, upd_dt: str = "26.01.2024 в 14:49", redis_db: Optional[redis.StrictRedis] = None):
        self.num: int = num
        self.status: bool = status
        self.upd_dt: datetime.datetime = datetime.datetime.strptime(upd_dt, self.FORMAT_DT)
        self.alert_func: Callable = lambda num, status, old_status, upd_dt, old_upd_dt: print(f"№{num} wash Mach — {'Занято' if status else 'СВОБОДНО'}")
        self._redis = None
        if redis_db:
            self._redis = WashMachRedis(redis_db)
        logger.info(f"Initialized WashMach #{num} with status {status}")

    @log_function(logger)
    def compare(self, num: int, status: bool, upd_dt: str) -> None:
        """Compare current status with new status and update if needed."""
        dt = self.upd_dt.timestamp()
        new_dt = datetime.datetime.strptime(upd_dt, self.FORMAT_DT).timestamp()
        
        if abs(new_dt - dt) > 0 and self.num == num:
            old_status = self.status
            self.status = status
            
            if old_status != status:
                old_upd_dt = self.upd_dt
                self.upd_dt = datetime.datetime.strptime(upd_dt, self.FORMAT_DT)
                
                if self._redis:
                    self._redis.write_by_num(num, self.get_info(from_redis=False))
                
                self.alert_func(num, status, old_status, upd_dt, old_upd_dt)
                logger.info(f"WashMach #{num} status changed from {old_status} to {status}")

    @log_function(logger)
    def _fill_from_db(self) -> None:
        """Refresh data from Redis."""
        if self._redis:
            data = self._redis.get_by_num(self.num)
            self.status = data['status']
            self.upd_dt = datetime.datetime.strptime(data['upd_dt'], self.FORMAT_DT)

    @log_function(logger)
    def get_info(self, from_redis: bool = True) -> Dict[str, Any]:
        """Get washing machine info, optionally refreshing from Redis first."""
        if from_redis:
            self._fill_from_db()
        return {
            "num": self.num,
            "status": self.status,
            "upd_dt": self.upd_dt.strftime(self.FORMAT_DT)
        }

    def to_string(self, date: bool = True) -> str:
        """Create string representation of washing machine status."""
        status_text = "‼️BUSY‼️" if self.status else "✅Free"
        date_info = f'\nДата обновления: {self.upd_dt}' if date else ""
        return f'🧻№{self.num}  - {status_text}{date_info}'


class UniMeter:
    """Class for fetching and processing washing machine data."""
    
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
        self.arr_washes: List[WashMach] = [WashMach(i, False, redis_db=self._redis) for i in range(1, 7)]
        logger.info("Initialized UniMeter with 6 washing machines")
        self.getData()

    @log_function(logger)
    def _fetch_from_website(self) -> List[WashMach]:
        """Fetch washing machine data from UniMeter website."""
        logger.info("Fetching data from UniMeter website")
        try:
            response = self.ses.get(
                "https://cabinet.unimetriq.com/client/6703b4b333805792cfa639770058bd45",
                headers=self.headers, 
                verify=False
            )
            undata = BeautifulSoup(response.content, "html.parser")
            
            # Find all washing machine blocks
            wash_blocks = undata.find_all("div", {"class": "col", "style": "min-width: 179px;max-width:195px;"})
            
            for i, block in enumerate(wash_blocks):
                if i >= len(self.arr_washes):
                    break
                    
                try:
                    self._process_machine_block(i, block, undata)
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error processing machine block {i}: {str(e)}")
                    continue
                
            return self.arr_washes
            
        except Exception as e:
            logger.error(f"Error fetching data from UniMeter website: {str(e)}")
            return self.arr_washes

    def _process_machine_block(self, index: int, block: Any, undata: BeautifulSoup) -> None:
        """Process a single washing machine block from the HTML."""
        # Check if machine is busy - explicitly look for danger
        is_busy = "border-danger" in str(block)
        
        # Determine status class and border class based on what's in the block
        if "border-danger" in str(block):
            border_class = "border-danger"
            status_class = "text-danger"
        elif "border-success" in str(block):
            border_class = "border-success"
            status_class = "text-success"
        else:
            # Handle unknown status class
            logger.warning(f"Unknown border class for machine block {index} - neither danger nor success found")
            border_class = None
            status_class = None
            is_busy = False  # Default to free if unknown
        
        # Find the machine number
        if border_class and status_class:
            number_div = block.find("div", {
                "class": lambda x: all(c in x for c in [f"{border_class}", "border", "border-3", f"{status_class}", 
                                                        "mx-auto", "mt-3", "mb-2", "rounded-circle"]),
                "style": lambda x: "width: 90px; height: 90px;" in x
            })
        else:
            # Try a more generic approach if status classes are unknown
            number_div = block.find("div", {
                "class": lambda x: "rounded-circle" in x and "border" in x and "mx-auto" in x,
                "style": lambda x: "width: 90px; height: 90px;" in x
            })
        
        if not number_div:
            logger.warning(f"Could not find number div for machine block {index}")
            return
            
        number = int(number_div.text.strip())
        
        # Try to find status text and determine busy state
        try:
            # First look for specific status class if available
            status_text = None
            if status_class:
                status_divs = block.find_all("div", {"class": lambda x: f"p-2 {status_class}" in x})
                if status_divs:
                    text_center = status_divs[-1].find("div", {"class": "text-center"})
                    if text_center:
                        status_text = text_center.text.strip()
            
            # If not found with specific class, try more generic approach
            if not status_text:
                status_divs = block.find_all("div", {"class": lambda x: "p-2" in x})
                if status_divs:
                    for div in status_divs:
                        text_center = div.find("div", {"class": "text-center"})
                        if text_center:
                            status_text = text_center.text.strip()
                            break
            
            # If still not found, log error and default to free
            if not status_text:
                logger.warning(f"Could not find status text for machine #{number} - defaulting to free")
                is_busy = False
            else:
                # Determine busy state based on text content
                is_busy = "анято" in status_text.lower()
                logger.debug(f"Found status text for machine #{number}: '{status_text}', busy: {is_busy}")
                
        except Exception as e:
            logger.error(f"Error determining status for machine #{number}: {str(e)} - defaulting to free")
            is_busy = False
        
        # Get last update time
        try:
            update_div = undata.find("div", {"data-toggle": "tooltip", "title": lambda x: x and "Последний обмен данными" in x})
            if not update_div:
                logger.warning(f"Could not find update time for machine #{number}")
                return
                
            update_time = update_div['title'].replace("Последний обмен данными ", "")
            
            logger.debug(f"Found machine #{number}: busy={is_busy}, update_time={update_time}")
            
            if self._redis:
                self.arr_washes[index].get_info()
                
            self.arr_washes[index].compare(
                num=number,
                status=is_busy,
                upd_dt=update_time
            )
        except Exception as e:
            logger.error(f"Error processing update time for machine #{number}: {str(e)}")

    def _fetch_from_redis(self) -> List[WashMach]:
        """Fetch washing machine data from Redis."""
        logger.info("Fetching data from Redis")
        for data_wash in self.arr_washes:
            data_wash.get_info()
        return self.arr_washes

    @log_function(logger)
    def getData(self) -> List[WashMach]:
        """Get washing machine data from appropriate source."""
        if not self._redis or self._server_mode:
            return self._fetch_from_website()
        else:
            return self._fetch_from_redis()


class RedisUser:
    """Class for managing user data in Redis."""
    
    def __init__(self, redis_db: redis.StrictRedis):
        self.redis_db = redis_db

    def name_db(self, num: int) -> str:
        """Get Redis key for wash alarmer by machine number."""
        return f'wash_alarmer:{num}'

    def clear_by_num(self, num: int) -> None:
        """Clear all users for a specific washing machine."""
        self.redis_db.delete(self.name_db(num))

    def add_user_data(self, user_id: str) -> None:
        """Increment user counter."""
        name = f"user:{user_id}"
        value = 0
        if self.redis_db.exists(name):
            value = int(self.redis_db.get(name).decode("utf-8"))
        self.redis_db.set(name, value=value+1)

    def add_by_num(self, num: int, user_id: str) -> None:
        """Add user to a washing machine's notification list."""
        self.redis_db.sadd(self.name_db(num), user_id)

    def remove_by_num(self, num: int, user_id: str) -> None:
        """Remove user from a washing machine's notification list."""
        self.redis_db.srem(self.name_db(num), user_id)

    def get_by_num(self, num: int) -> List[str]:
        """Get all users for a washing machine."""
        data = self.redis_db.smembers(self.name_db(num))
        return [x.decode("utf-8") for x in data]

    def pop_by_num(self, num: int) -> List[str]:
        """Pop all users from a washing machine's notification list."""
        result = []
        while True:
            popped_element = self.redis_db.spop(self.name_db(num))
            if popped_element is None:
                break
            result.append(popped_element.decode("utf-8"))
        return result