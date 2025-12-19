import logging
from logging.handlers import RotatingFileHandler


_logger = None


def get_logger():
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Rotating file handler (optional; ignored if file not permitted)
    try:
        fh = RotatingFileHandler("app.log", maxBytes=512000, backupCount=3)
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception:
        pass

    _logger = logger
    return logger


def log_exception(err: Exception, context: str = ""):
    logger = get_logger()
    try:
        logger.exception(f"{context} {err}")
    except Exception:
        # Best-effort logging
        print(f"ERROR: {context} {err}")


