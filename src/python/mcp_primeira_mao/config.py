import os
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Logger centralizado
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"saga_api_{datetime.now().strftime('%Y%m%d')}.log"),
    ],
)
logger = logging.getLogger("PrimeiraMaoSaga")

# Constantes
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}

URL_AWS_TOKEN = os.getenv("URL_AWS_TOKEN", "")
MOBI_SECRET = os.getenv("MOBI_SECRET", "")
PRECIFICACAO_API_URL = os.getenv("PRECIFICACAO_API_URL", "")
TIMEOUT = int(os.getenv("API_TIMEOUT", "15"))