"""
File system Utilities - This module provides functionality
to query, navigate, and manipulate files and directories.
"""

"""
@author: Chris Lamke
"""


import os

def is_dir_readable(directory_path):
    # BUGFIX: this previously only checked os.F_OK (existence), not os.R_OK
    # (read permission), despite the function name promising a readability
    # check. A directory that exists but isn't readable would have incorrectly
    # returned True.
    if (os.access(directory_path, os.F_OK)):
        if (os.access(directory_path, os.R_OK)):
            return True
        else:
            return False
    else:
        return False


def is_dir_writable(directory_path):
    if (os.access(directory_path, os.F_OK)):
        if (os.access(directory_path, os.W_OK)):
            return True
        else:
            return False
    else:
        return False


def is_file_readable(file_path):
    if (os.access(file_path, os.F_OK)):
        if (os.access(file_path, os.R_OK)):
            return True
        else:
            return False
    else:
        return False

def is_file_writable(file_path):
    if (os.access(file_path, os.F_OK)):
        if (os.access(file_path, os.W_OK)):
            return True
        else:
            return False
    else:
        return False
