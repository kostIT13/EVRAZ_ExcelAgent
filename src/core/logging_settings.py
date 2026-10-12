from loguru import logger
import sys
from pathlib import Path
from src.core.config import settings


logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - {message}",
    level=settings.LOG_LEVEL,
)
# Файловый лог — опционально: в свежем checkout (CI) директории logs/ может
# не существовать (git не хранит пустые директории), поэтому создаём её
# и при ошибке (нет прав и т.п.) продолжаем писать только в stderr.

try:
    Path("logs").mkdir(parents=True, exist_ok=True)
    logger.add("logs/app.log", rotation="10 MB", retention="7 days", level=settings.LOG_LEVEL)
except Exception:
    logger.warning("Не удалось настроить файловый лог — пишем только в stderr")


