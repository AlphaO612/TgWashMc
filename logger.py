import logging
import functools
import time
from typing import Callable, Any
import json

# Настраиваем базовый logger
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def setup_logger(name: str) -> logging.Logger:
    """Создает и возвращает настроенный logger"""
    logger = logging.getLogger(name)
    
    # Добавляем обработчик для записи в файл
    file_handler = logging.FileHandler(f'{name}.log')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(file_handler)
    
    return logger

def log_function(logger: logging.Logger):
    """Декоратор для логирования функций"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            
            # Подготовка информации для логирования
            log_data = {
                'function': func.__name__,
                'args': str(args),
                'kwargs': str(kwargs),
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                log_data.update({
                    'status': 'success',
                    'execution_time': f'{execution_time:.4f}s',
                    'result': str(result)
                })
                
                logger.debug(json.dumps(log_data))
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                
                log_data.update({
                    'status': 'error',
                    'error': str(e),
                    'execution_time': f'{execution_time:.4f}s'
                })
                
                logger.error(json.dumps(log_data))
                raise
                
        return wrapper
    return decorator 