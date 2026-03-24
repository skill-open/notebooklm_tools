#!/usr/bin/env python3
"""
NotebookLM 源文件内容整理脚本

功能：整理 NotebookLM 笔记本中所有源文件的核心内容，并输出为 Markdown 文件
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from notebooklm.rpc.types import SourceStatus

from ..core import sanitize_filename, log_message, parse_indices
from ..client import check_login_status, list_notebooks, list_sources


async def configure_chat(notebook_id: str, persona: str, response_length: str = "longer"):
    """配置聊天角色"""
    from notebooklm.client import NotebookLMClient
    from notebooklm.rpc import ChatGoal, ChatResponseLength
    
    length_map = {
        "default": ChatResponseLength.DEFAULT,
        "longer": ChatResponseLength.LONGER,
        "shorter": ChatResponseLength.SHORTER,
    }
    
    async with await NotebookLMClient.from_storage() as client:
        await client.chat.configure(
            notebook_id,
            goal=ChatGoal.CUSTOM if persona else None,
            response_length=length_map.get(response_length, ChatResponseLength.LONGER),
            custom_prompt=persona
        )
        print(f"✓ 已配置聊天角色")


async def ask_question(notebook_id: str, question: str, source_id: str = None) -> dict:
    """向笔记本提问"""
    from notebooklm.client import NotebookLMClient
    
    async with await NotebookLMClient.from_storage() as client:
        source_ids = [source_id] if source_id else None
        result = await client.chat.ask(
            notebook_id,
            question,
            source_ids=source_ids
        )
        return {
            "answer": result.answer,
            "conversation_id": result.conversation_id,
            "is_follow_up": result.is_follow_up,
            "turn_number": result.turn_number
        }


async def process_source(
    notebook_id: str,
    notebook_name: str,
    source: dict,
    question: str,
    output_dir: Path,
    log_file: Path
) -> bool:
    """处理单个源文件
    
    Args:
        notebook_id: 笔记本 ID
        notebook_name: 笔记本名称
        source: 源文件信息
        question: 提问内容
        output_dir: 输出目录
        log_file: 日志文件路径
    
    Returns:
        bool: 是否成功
    """
    source_id = source["id"]
    source_title = source["title"]
    
    # 检查源文件状态（READY = 2 表示已完成）
    if source["status"] != SourceStatus.READY:
        log_message(f"⊘ 跳过未完成的源文件：{source_title} ({source_id})", log_file)
        return False
    
    # 清理文件名并移除扩展名
    safe_title = sanitize_filename(Path(source_title).stem)
    output_filename = f"{safe_title}_整理.md"
    output_path = output_dir / output_filename
    
    # 检查文件是否已存在
    if output_path.exists():
        log_message(f"⊘ 跳过已存在的文件：{output_filename}", log_file)
        return False
    
    # 提问
    log_message(f"→ 开始处理源文件：{source_title} ({source_id})", log_file)
    
    try:
        result = await ask_question(notebook_id, question, source_id)
        
        # 保存结果
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result["answer"])
        
        log_message(f"✓ 完成：{output_filename}", log_file)
        return True
        
    except Exception as e:
        log_message(f"✗ 失败：{source_title} - {e}", log_file)
        return False


async def process_source_batch(
    notebook_id: str,
    notebook_name: str,
    sources: List[dict],
    question: str,
    output_dir: Path,
    log_file: Path
):
    """批量处理源文件
    
    Args:
        notebook_id: 笔记本 ID
        notebook_name: 笔记本名称
        sources: 源文件列表
        question: 提问内容
        output_dir: 输出目录
        log_file: 日志文件路径
    """
    log_message("\n" + "=" * 60, log_file)
    log_message("开始处理源文件...", log_file)
    log_message(f"源文件数量：{len(sources)}", log_file)
    log_message("=" * 60, log_file)
    
    success_count = 0
    fail_count = 0
    
    for i, source in enumerate(sources, 1):
        print(f"\n[{i}/{len(sources)}]", end=" ")
        
        success = await process_source(
            notebook_id=notebook_id,
            notebook_name=notebook_name,
            source=source,
            question=question,
            output_dir=output_dir,
            log_file=log_file
        )
        
        if success:
            success_count += 1
        else:
            fail_count += 1
    
    # 完成统计
    log_message("\n" + "=" * 60, log_file)
    log_message("处理完成统计", log_file)
    log_message("=" * 60, log_file)
    log_message(f"总计：{len(sources)}", log_file)
    log_message(f"成功：{success_count}", log_file)
    log_message(f"失败：{fail_count}", log_file)
    success_rate = (success_count / len(sources) * 100) if len(sources) > 0 else 0
    log_message(f"成功率：{success_rate:.1f}%", log_file)
    log_message(f"输出目录：{output_dir}", log_file)
    log_message(f"日志文件：{log_file}", log_file)


async def main():
    """主函数"""
    print("=" * 60)
    print("NotebookLM 源文件内容整理工具")
    print("=" * 60)
    
    # 检查登录状态
    print("\n[步骤 1] 检查登录状态...")
    if not await check_login_status():
        print("✗ 未登录，请先运行：notebooklm login")
        print("  提示：登录后请重新执行该命令")
        return
    
    print("✓ 已登录")
    
    # 列出笔记本
    print("\n[步骤 2] 列出所有笔记本...")
    notebooks = await list_notebooks()
    
    if not notebooks:
        print("✗ 没有找到笔记本")
        return
    
    print("\n可用笔记本:")
    for i, nb in enumerate(notebooks, 1):
        owner = "Owner" if nb["is_owner"] else "Shared"
        created = nb["created_at"][:10] if nb["created_at"] else "-"
        print(f"  {i}. {nb['title']}")
        print(f"     ID: {nb['id']}")
        print(f"     类型：{owner}, 创建时间：{created}")
        print()
    
    # 选择笔记本
    while True:
        notebook_choice = input("请选择笔记本编号 (1-{}): ".format(len(notebooks)))
        try:
            notebook_index = int(notebook_choice) - 1
            if 0 <= notebook_index < len(notebooks):
                notebook = notebooks[notebook_index]
                notebook_id = notebook["id"]
                notebook_name = notebook["title"]
                break
            else:
                print("✗ 无效的选择，请输入正确的编号")
        except ValueError:
            print("✗ 无效的输入，请输入数字")
    
    print(f"\n✓ 已选择笔记本：{notebook_name}")
    
    # 获取源文件列表
    print(f"\n[步骤 3] 获取源文件列表...")
    sources = await list_sources(notebook_id)
    
    if not sources:
        print("✗ 笔记本中没有源文件")
        return
    
    print(f"\n找到 {len(sources)} 个源文件:")
    for i, source in enumerate(sources, 1):
        status_icon = "✓" if source["status"] == SourceStatus.READY else "⊘"
        print(f"  {i}. {status_icon} {source['title']}")
        print(f"     类型：{source['type']}, 状态：{source['status']}")
        print()
    
    # 选择处理方式
    print("\n[步骤 4] 选择处理方式:")
    print("  1. 处理所有源文件")
    print("  2. 选择特定源文件（输入编号，多个用逗号分隔，支持范围格式如 2-5）")
    print("  3. 跳过已处理的源文件（输入编号，多个用逗号分隔，支持范围格式如 2-5）")
    
    while True:
        choice = input("\n请输入选项 (1/2/3) [默认：1]: ").strip() or "1"
        if choice in ["1", "2", "3"]:
            break
        print("✗ 无效的选项，请输入 1、2 或 3")
    
    selected_sources = []
    
    if choice == "1":
        selected_sources = sources
        print(f"✓ 将处理所有 {len(selected_sources)} 个源文件")
        
    elif choice == "2":
        while True:
            indices = input("请输入要处理的源文件编号（多个用逗号分隔，支持范围格式如 2-5）: ").strip()
            try:
                valid_indices = parse_indices(indices, len(sources))
                if not valid_indices:
                    print("✗ 没有有效的源文件编号，请重新输入")
                    continue
                selected_sources = [sources[i] for i in valid_indices]
                print(f"✓ 将处理 {len(selected_sources)} 个源文件")
                break
            except Exception as e:
                print(f"✗ 发生错误：{e}")
            
    elif choice == "3":
        while True:
            indices = input("请输入要跳过的源文件编号（多个用逗号分隔，支持范围格式如 2-5）: ").strip()
            try:
                skip_indices = parse_indices(indices, len(sources))
                skip_set = set(skip_indices)
                selected_sources = [sources[i] for i in range(len(sources)) if i not in skip_set]
                print(f"✓ 将处理 {len(selected_sources)} 个源文件")
                break
            except Exception as e:
                print(f"✗ 发生错误：{e}")
    
    # 过滤未就绪的源文件
    ready_sources = [s for s in selected_sources if s["status"] == SourceStatus.READY]
    skipped_sources = [s for s in selected_sources if s["status"] != SourceStatus.READY]
    
    if skipped_sources:
        print(f"\n⚠ 跳过 {len(skipped_sources)} 个未就绪的源文件")
        print("  提示：只有状态为 'READY' 的源文件才能处理")
    
    if not ready_sources:
        print("✗ 没有就绪的源文件可以处理")
        print("  提示：请等待源文件处理完成后再尝试")
        return
    
    print(f"✓ 将处理 {len(ready_sources)} 个就绪的源文件")
    
    # 配置聊天角色
    print("\n[步骤 5] 配置聊天角色...")
    configure_choice = input("是否配置聊天角色？(Y/n) [默认：Y]: ").strip().lower()
    
    persona = "你是个文档整理专家，善于整理文档的核心内容。你主要就是把我给你的文档整理下，输出文档的核心内容。"
    response_length = "longer"
    
    if configure_choice != "n":
        # 步骤 1: 配置 persona
        print("\n[配置 1/2] 聊天角色 (--persona):")
        default_persona = "你是个文档整理专家，善于整理文档的核心内容。你主要就是把我给你的文档整理下，输出文档的核心内容。"
        
        persona_choice = input(f"是否使用默认角色？(Y/n) [默认：Y]: ").strip().lower()
        if persona_choice != "n":
            persona = default_persona
            print(f"使用默认角色：{persona}")
        else:
            persona = input("请输入自定义角色：").strip()
            if not persona:
                persona = default_persona
                print(f"使用默认角色：{persona}")
            else:
                print(f"已设置角色：{persona}")
        
        # 步骤 2: 配置 response-length
        print("\n[配置 2/2] 响应长度 (--response-length):")
        print("  1. default - 默认长度")
        print("  2. longer - 较长 (默认)")
        print("  3. shorter - 较短")
        length_choice = input("请选择 (1-3) [默认：2]: ").strip() or "2"
        
        length_map = {
            "1": "default",
            "2": "longer",
            "3": "shorter"
        }
        response_length = length_map.get(length_choice, "longer")
        
        length_display = {
            "default": "默认",
            "longer": "较长",
            "shorter": "较短"
        }
        print(f"已设置响应长度：{length_display[response_length]}")
        
        # 执行配置
        await configure_chat(notebook_id, persona, response_length)
    else:
        print("⊘ 跳过聊天角色配置")
    
    # 创建输出目录
    print(f"\n[步骤 6] 创建输出目录...")
    safe_notebook_name = sanitize_filename(notebook_name)
    output_dir = Path("./output") / f"{safe_notebook_name}_organized"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"✓ 输出目录：{output_dir}")
    except Exception as e:
        print(f"✗ 创建输出目录失败：{e}")
        return
    
    # 创建日志文件
    log_file = output_dir / "source_organization.log"
    log_message("=" * 60, log_file, "INFO")
    log_message("开始源文件整理任务", log_file, "INFO")
    log_message(f"笔记本：{notebook_name} ({notebook_id})", log_file, "INFO")
    log_message(f"聊天角色：{persona}", log_file, "INFO")
    log_message(f"响应长度：{response_length}", log_file, "INFO")
    log_message(f"源文件数量：{len(ready_sources)}", log_file, "INFO")
    log_message("=" * 60, log_file, "INFO")
    
    # 处理源文件
    print(f"\n[步骤 7] 开始批量整理源文件...")
    print("=" * 60)
    print(f"将为 {len(ready_sources)} 个源文件生成整理内容")
    print("=" * 60)
    
    question = "整理信息"
    await process_source_batch(
        notebook_id=notebook_id,
        notebook_name=notebook_name,
        sources=ready_sources,
        question=question,
        output_dir=output_dir,
        log_file=log_file
    )
    
    # 完成
    print("\n" + "=" * 60)
    print("✓ 所有源文件处理完成!")
    print(f"  输出目录：{output_dir}")
    print(f"  日志文件：{log_file}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
