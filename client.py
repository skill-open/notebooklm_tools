#!/usr/bin/env python3
"""
NotebookLM client interactions
"""

from typing import List, Dict, Optional
from notebooklm.client import NotebookLMClient


async def check_login_status() -> bool:
    """检查登录状态"""
    try:
        async with await NotebookLMClient.from_storage() as client:
            notebooks = await client.notebooks.list()
            return len(notebooks) > 0
    except Exception as e:
        print(f"登录检查失败: {e}")
        return False


async def list_notebooks() -> List[Dict[str, any]]:
    """列出所有笔记本"""
    try:
        async with await NotebookLMClient.from_storage() as client:
            notebooks = await client.notebooks.list()
            return [
                {
                    "id": nb.id,
                    "title": nb.title,
                    "is_owner": nb.is_owner,
                    "created_at": nb.created_at.isoformat() if nb.created_at else None
                }
                for nb in notebooks
            ]
    except Exception as e:
        from .utils import log_message
        log_message(f"获取笔记本列表失败: {e}")
        return []


async def list_sources(notebook_id: str) -> List[Dict[str, any]]:
    """列出笔记本中的所有源文件"""
    try:
        async with await NotebookLMClient.from_storage() as client:
            sources = await client.sources.list(notebook_id)
            return [
                {
                    "id": src.id,
                    "title": src.title or "(untitled)",
                    "type": str(src.kind),
                    "url": src.url,
                    "status": src.status,
                    "created_at": src.created_at.isoformat() if src.created_at else None
                }
                for src in sources
            ]
    except Exception as e:
        from .utils import log_message
        log_message(f"获取源文件列表失败: {e}")
        return []