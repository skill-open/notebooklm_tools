#!/usr/bin/env python3
"""
NotebookLM generators module
"""

def __getattr__(name):
    """延迟导入，避免模块重复加载警告"""
    if name == 'infographics_main':
        from .infographics import main as infographics_main
        return infographics_main
    elif name == 'ppts_main':
        from .ppts import main as ppts_main
        return ppts_main
    elif name == 'videos_main':
        from .videos import main as videos_main
        return videos_main
    elif name == 'source_organizer_main':
        from .source_organizer import main as source_organizer_main
        return source_organizer_main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ['infographics_main', 'ppts_main', 'videos_main', 'source_organizer_main']
