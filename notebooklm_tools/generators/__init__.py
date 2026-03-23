#!/usr/bin/env python3
"""
NotebookLM generators module
"""

from .infographics import main as infographics_main
from .ppts import main as ppts_main
from .videos import main as videos_main

__all__ = ['infographics_main', 'ppts_main', 'videos_main']
