import logging
from pathlib import Path

from core import config


def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("toon_flow")
    if logger.handlers:
        return logger

    level = logging.DEBUG if config.DEBUG_MODE else logging.INFO
    logger.setLevel(level)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(fmt)

    logger.addHandler(stream_handler)

    # ファイルログは任意（権限/実行環境によっては作れないため、失敗しても致命にしない）
    try:
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except Exception:
        # StreamHandlerのみで継続
        pass

    logger.propagate = False
    return logger


logger = _setup_logging()

