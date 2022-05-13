import logging
from logging import handlers
import os

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger_name = 'jawa'
log_roll_size = (1048576 * 100)
log_backupCount = 10

def setup_logger(log_name, log_filename):
    # log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'jawa.log'))

    log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
    print(f'log_path: {log_path}')
    if not os.path.isdir(log_path):
        os.makedirs(log_path)
    log_file = os.path.join(log_path, log_filename)
    print(f'log_file: {log_file}')
    handler = handlers.RotatingFileHandler(log_file, maxBytes=log_roll_size, backupCount=log_backupCount)
    handler.setFormatter(formatter)
    logger = logging.getLogger(log_name)
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)
    # if settings.debug_mode:
    #     logger.setLevel(logging.DEBUG)
    # else:
    logger.setLevel(logging.DEBUG)
    return logger


def setup_child_logger(name):
    return logging.getLogger(logger_name).getChild(name)


logthis = setup_logger(logger_name, f'{logger_name}.log')
logthis.debug('this got logged by the main logger')