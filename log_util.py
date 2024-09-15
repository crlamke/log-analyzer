"""
Log Utilities - This module provides logging functionality.
"""

"""
@author: Chris Lamke
"""

import os
import sys

import logging
from enum import Enum

class LogLevel(Enum):
    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4
    FATAL = 5

""" Logger class that does all the logging work"""
class Logger:
    def __init__(self, logfile_path, logfile_name):
        self.logfile_name = logfile_name
        self.logfile_path = logfile_path
        self.logfile = os.path.join(logfile_path, logfile_name)
        self.log_formatter = logging.Formatter(
            "%(asctime)s  %(message)s", '%Y-%m-%d-%H:%M:%S')
            #"%(asctime)s [%(threadName)s] [%(levelname)s]  %(message)s", '%Y-%m-%d %H:%M:%S')
        self.root_logger = logging.getLogger()
        self.root_logger.setLevel(logging.INFO)
        self.logfile_handler = logging.FileHandler(self.logfile)
        self.logfile_handler.setFormatter(self.log_formatter)
        self.root_logger.addHandler(self.logfile_handler)
        self.console_handler = logging.StreamHandler(sys.stdout)
        self.console_handler.setFormatter(self.log_formatter)
        self.root_logger.addHandler(self.console_handler)
    
    def debug(self, logtext):
        logging.debug(logtext)

    def info(self, logtext):
        logging.info(logtext)

    def warning(self, logtext):
        logging.warning(logtext)

    def error(self, logtext):
        logging.error(logtext)

    def fatal(self, logtext):
        logging.critical(logtext)

    def shutdown(self):
        logging.shutdown()
