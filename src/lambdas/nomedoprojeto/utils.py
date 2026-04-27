import json
import logging

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

def log(message: str, level: str = "INFO"):
    getattr(_logger, level.lower(), _logger.info)(message)

def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
