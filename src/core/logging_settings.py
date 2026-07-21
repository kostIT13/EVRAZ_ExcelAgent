from loguru import logger
import sys 
from src.core.config import settings


logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - {message}",
    level=settings.LOG_LEVEL, 
)
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level=settings.LOG_LEVEL)


