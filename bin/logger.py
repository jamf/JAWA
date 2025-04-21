# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2022 Jamf.  All rights reserved.
#
#       Redistribution and use in source and binary forms, with or without
#       modification, are permitted provided that the following conditions are met:
#               * Redistributions of source code must retain the above copyright
#                 notice, this list of conditions and the following disclaimer.
#               * Redistributions in binary form must reproduce the above copyright
#                 notice, this list of conditions and the following disclaimer in the
#                 documentation and/or other materials provided with the distribution.
#               * Neither the name of the Jamf nor the names of its contributors may be
#                 used to endorse or promote products derived from this software without
#                 specific prior written permission.
#
#       THIS SOFTWARE IS PROVIDED BY JAMF SOFTWARE, LLC "AS IS" AND ANY
#       EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#       WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#       DISCLAIMED. IN NO EVENT SHALL JAMF SOFTWARE, LLC BE LIABLE FOR ANY
#       DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
#       (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#       LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
#       ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#       (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#       SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

import logging
from logging import handlers
import os
from typing import Optional

formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger_name = 'jawa'
default_log_level = logging.INFO
log_roll_size = 1048576 * 100
log_backupCount = 10


def setup_logger(
    log_name: Optional[str] = logger_name,
    log_filename: Optional[str] = f'{logger_name}.log',
    log_level: Optional[int] = default_log_level,
) -> logging.Logger:
    log_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'data')
    )
    if not os.path.isdir(log_path):
        os.makedirs(log_path)
    log_file = os.path.join(log_path, log_filename)
    handler = handlers.RotatingFileHandler(
        log_file, maxBytes=log_roll_size, backupCount=log_backupCount
    )
    handler.setFormatter(formatter)
    logger = logging.getLogger(log_name)
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(log_level)
    return logger


def setup_child_logger(
    name_of_logger: str, name_of_child: str
) -> logging.Logger:
    return logging.getLogger(name_of_logger).getChild(name_of_child)


logthis = setup_logger(logger_name, f'{logger_name}.log')
