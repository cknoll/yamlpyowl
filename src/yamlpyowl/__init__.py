# -*- coding: utf-8 -*-

try:
    from .core import *
except ImportError:
    # this might be relevant during the installation process
    # otherwise setup.py cannot be executed
    pass

from .release import __version__
