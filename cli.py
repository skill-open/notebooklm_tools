#!/usr/bin/env python3
"""
CLI interaction functions for NotebookLM tools
"""

from typing import List, Tuple, Optional


LANGUAGE_MAP = {
    "1": "zh_Hans",
    "2": "zh_Hant",
    "3": "en",
    "4": "ja",
    "5": "ko"
}


def get_user_choice(prompt: str, options: List[Tuple[str, str]], default: str) -> str:
    """获取用户选择"""
    print(f"\n[{prompt}]")
    for i, (key, desc) in enumerate(options, 1):
        print(f"  {i}. {key} - {desc}")
    
    choice = input(f"请选择 (1-{len(options)}) [默认: {default}]: ").strip() or default
    return choice


def get_language_choice() -> str:
    """获取语言选择"""
    options = [
        ("zh_Hans", "简体中文 (默认)"),
        ("zh_Hant", "繁体中文"),
        ("en", "英文"),
        ("ja", "日文"),
        ("ko", "韩文"),
        ("其他", "手动输入")
    ]
    
    choice = get_user_choice("语言选择", options, "1")
    
    if choice == "6":
        return input("请输入语言代码 (如 fr, de, es): ").strip() or "zh_Hans"
    
    return LANGUAGE_MAP.get(choice, "zh_Hans")


def get_instructions(default_instructions: str) -> Optional[str]:
    """获取生成提示词"""
    print("\n[生成提示词]")
    print(f"默认提示词: {default_instructions}")
    use_default = input(f"是否使用默认提示词? (Y/n) [默认: Y]: ").strip().lower()
    
    if use_default != "n":
        return default_instructions
    
    custom = input("请输入自定义提示词: ").strip()
    return custom if custom else default_instructions