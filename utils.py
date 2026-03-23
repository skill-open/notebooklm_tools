#!/usr/bin/env python3
"""
Utility functions for NotebookLM tools
"""

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Tuple


def sanitize_filename(filename: str) -> str:
    """清理文件名中的特殊字符"""
    invalid_chars = r'[<>:"/\\|?*]'
    return re.sub(invalid_chars, '_', filename)


def log_message(message: str, log_file: Path = None, level: str = "INFO"):
    """记录日志消息"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}"
    
    # 只有INFO级别以上的消息才打印到控制台
    if level in ["INFO", "WARNING", "ERROR"]:
        print(log_line)
    
    if log_file:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")


def run_command(cmd: str, timeout: int = 30) -> Tuple[int, str, str]:
    """运行命令并返回结果
    
    Args:
        cmd: 要执行的命令
        timeout: 超时时间（秒）
    
    Returns:
        Tuple[int, str, str]: (返回码, 标准输出, 标准错误)
    """
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", f"命令执行超时（{timeout}秒）"
    except Exception as e:
        return 1, "", str(e)


def parse_indices(input_str: str, max_index: int) -> list:
    """解析输入的编号，支持单个数字和范围格式
    
    Args:
        input_str: 输入字符串，如 "1,3-5,7"
        max_index: 最大有效索引
    
    Returns:
        List[int]: 解析后的索引列表（从0开始）
    """
    indices = []
    parts = input_str.split(",")
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        if "-" in part:
            # 处理范围格式，如 "2-5"
            try:
                start, end = part.split("-")
                start = int(start.strip())
                end = int(end.strip())
                # 确保范围是有效的
                if start <= end:
                    # 将编号转换为索引（从0开始）
                    for i in range(start, end + 1):
                        index = i - 1
                        if 0 <= index < max_index:
                            indices.append(index)
            except ValueError:
                pass
        else:
            # 处理单个数字
            try:
                index = int(part) - 1
                if 0 <= index < max_index:
                    indices.append(index)
            except ValueError:
                pass
    
    # 去重并排序
    return sorted(list(set(indices)))