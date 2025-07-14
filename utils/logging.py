import logging
import sys

from utils.config import LOG_LEVEL

# Configure the logger
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# Get the logger
logger = logging.getLogger(__name__)
