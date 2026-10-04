import logging
import os

def setup_logger(name: str, log_file: str = "bot/logs/app.log", level=logging.INFO):
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",datefmt="%Y-%m-%d %H:%M:%S")

        #file handler, write to app.log
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        #stream handler, print log to terminal output for user
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger