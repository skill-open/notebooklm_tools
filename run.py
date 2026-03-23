#!/usr/bin/env python3
"""
NotebookLM 工具统一入口脚本

功能：
1. 信息图生成
2. PPT 生成
3. 视频生成
"""

import asyncio
import sys

from notebooklm_tools.generators import infographics_main, ppts_main, videos_main

def print_menu():
    """打印菜单"""
    print("=" * 70)
    print("NotebookLM 工具集")
    print("=" * 70)
    print("1. 生成信息图")
    print("2. 生成 PPT")
    print("3. 生成视频")
    print("4. 退出")
    print("=" * 70)

def get_choice():
    """获取用户选择"""
    while True:
        choice = input("请选择功能编号 (1-4): ").strip()
        if choice in ["1", "2", "3", "4"]:
            return choice
        print("✗ 无效的选择，请输入 1-4 之间的数字")

async def main():
    """主函数"""
    while True:
        print_menu()
        choice = get_choice()
        
        if choice == "1":
            print("\n启动信息图生成工具...")
            await infographics_main()
        elif choice == "2":
            print("\n启动 PPT 生成工具...")
            await ppts_main()
        elif choice == "3":
            print("\n启动视频生成工具...")
            await videos_main()
        elif choice == "4":
            print("\n再见！")
            break
        
        # 完成后返回菜单
        input("\n按回车键返回主菜单...")

if __name__ == "__main__":
    asyncio.run(main())
