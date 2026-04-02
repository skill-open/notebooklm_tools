#!/usr/bin/env python3
"""
NotebookLM PPT 生成脚本

功能：为 NotebookLM 笔记本中的源文件批量生成 PPT，并自动下载
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from notebooklm.rpc.types import SourceStatus



from ..core import sanitize_filename, log_message, run_command, parse_indices
from ..client import check_login_status, list_notebooks, list_sources
from ..core.task import BaseGenerationTask, submit_generation_tasks, poll_task_statuses
from ..cli import get_language_choice, get_instructions


# 配置常量
MAX_CHECK_ROUNDS = 20  # 最多等待 20 分钟
CHECK_INTERVAL = 60  # 检查间隔（秒）
DEFAULT_INSTRUCTIONS = "手绘风格"
DOWNLOAD_TIMEOUT = 90  # 下载超时时间（秒）
MAX_DOWNLOAD_RETRIES = 5  # 最大下载重试次数

# 映射字典
PPT_FORMAT_MAP = {
    "1": "detailed",
    "2": "presentation"
}

PPT_LENGTH_MAP = {
    "1": "default",
    "2": "short",
    "3": "long"
}


@dataclass
class PPTGenerationTask(BaseGenerationTask):
    """PPT生成任务"""
    pass


async def submit_ppt_generation(
    notebook_id: str,
    source_id: str,
    ppt_format: str,
    ppt_length: str,
    language: str,
    instructions: str
) -> str:
    """
    提交PPT生成任务
    
    Returns:
        artifact_id: 生成的 artifact ID
    """
    cmd = f'notebooklm generate slide-deck --notebook {notebook_id} --source {source_id} --format {ppt_format} --length {ppt_length} --language {language} "{instructions}" --json'
    
    code, stdout, stderr = run_command(cmd)
    
    if code != 0:
        raise Exception(f"提交PPT生成失败: {stderr}")
    
    try:
        result = json.loads(stdout)
        if "task_id" in result:
            return result["task_id"]
        elif "error" in result:
            raise Exception(f"API错误: {result['error']}")
        else:
            raise Exception(f"未找到 task_id，响应: {stdout}")
    except json.JSONDecodeError:
        raise Exception(f"解析JSON失败: {stdout}")


async def check_ppt_status(notebook_id: str, artifact_id: str) -> Optional[dict]:
    """
    检查PPT生成状态
    
    Returns:
        dict with keys: status (str), is_complete (bool), is_failed (bool)
    """
    cmd = f'notebooklm artifact list --notebook {notebook_id} --type slide-deck --json'
    code, stdout, stderr = run_command(cmd)
    
    if code != 0:
        return {"error": f"获取状态失败: {stderr}"}
    
    try:
        result = json.loads(stdout)
        if "error" in result:
            return {"error": f"API错误: {result['error']}"}
        
        artifacts = result.get('artifacts', [])
        
        for artifact in artifacts:
            if artifact.get('id') == artifact_id:
                status = artifact.get('status', 'pending')
                return {
                    "status": status,
                    "is_complete": status == "completed",
                    "is_failed": status == "failed",
                    "title": artifact.get('title', '')
                }
        
        return {"error": f"未找到artifact_id: {artifact_id}"}
    except json.JSONDecodeError:
        return {"error": f"解析JSON失败: {stdout}"}


async def download_ppt(
    notebook_id: str,
    artifact_id: str,
    output_path: Path,
    retry_count: int = 0
) -> bool:
    """
    下载 PPT（带重试机制）
    
    Args:
        notebook_id: 笔记本 ID
        artifact_id: artifact ID
        output_path: 输出路径
        retry_count: 当前重试次数
    
    Returns:
        bool: 是否成功
    """
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = f'notebooklm download slide-deck --notebook {notebook_id} -a {artifact_id} "{str(output_path)}"'
    code, stdout, stderr = run_command(cmd, timeout=DOWNLOAD_TIMEOUT)
    
    if code == 0:
        return True
    else:
        # 下载失败，检查是否需要重试
        if retry_count < MAX_DOWNLOAD_RETRIES:
            print(f"  下载失败，{retry_count + 1}/{MAX_DOWNLOAD_RETRIES} 次重试中...：{stderr}")
            await asyncio.sleep(2 ** retry_count)  # 指数退避：2, 4, 8, 16, 32 秒
            return await download_ppt(notebook_id, artifact_id, output_path, retry_count + 1)
        else:
            print(f"  下载失败（已重试{MAX_DOWNLOAD_RETRIES}次）: {stderr}")
            return False


def get_ppt_format_choice() -> str:
    """获取PPT格式选择"""
    print("\n[PPT格式选择]")
    print("  1. detailed - 详细格式 (默认)")
    print("  2. presentation - 演示格式")
    
    choice: str = input("请选择 (1-2) [默认: 1]: ").strip() or "1"
    
    return PPT_FORMAT_MAP.get(choice, "detailed")


def get_ppt_length_choice() -> str:
    """获取PPT长度选择"""
    print("\n[PPT长度选择]")
    print("  1. default - 标准长度 (默认)")
    print("  2. short - 简短")

    
    choice: str = input("请选择 (1-2) [默认: 1]: ").strip() or "1"
    
    return PPT_LENGTH_MAP.get(choice, "default")


async def check_all_ppt_statuses(notebook_id: str) -> Dict[str, dict]:
    """批量检查所有PPT状态"""
    cmd = f'notebooklm artifact list --notebook {notebook_id} --type slide-deck --json'
    code, stdout, stderr = run_command(cmd)
    if code != 0:
        return {}
    try:
        result = json.loads(stdout)
        artifacts = result.get('artifacts', [])
        status_map = {}
        for artifact in artifacts:
            artifact_id = artifact.get('id')
            if artifact_id:
                status = artifact.get('status', 'pending')
                status_map[artifact_id] = {
                    "status": status,
                    "is_complete": status == "completed",
                    "is_failed": status == "failed",
                    "title": artifact.get('title', '')
                }
        return status_map
    except json.JSONDecodeError:
        return {}


async def process_ppt_batch(
    notebook_id: str,
    notebook_name: str,
    tasks: List[PPTGenerationTask],
    ppt_format: str,
    ppt_length: str,
    language: str,
    instructions: str,
    output_dir: Path,
    log_file: Path
):
    """
    批量处理 PPT 生成任务
    
    策略：
    1. 提交生成任务
    2. 如果达到请求上限，停止提交
    3. 轮询检查状态，每 1 分钟检查一次
    4. 完成的立即下载
    """
    # 提交所有生成任务
    async def submit_func(notebook_id, source_id, task):
        artifact_id = await submit_ppt_generation(
            notebook_id=notebook_id,
            source_id=source_id,
            ppt_format=ppt_format,
            ppt_length=ppt_length,
            language=language,
            instructions=instructions
        )
        return artifact_id
    
    submitted_count, reached_limit = await submit_generation_tasks(
        notebook_id=notebook_id,
        tasks=tasks,
        submit_func=submit_func,
        log_file=log_file
    )
    
    if submitted_count == 0:
        log_message("没有成功提交的任务，结束处理", log_file, "INFO")
        return
    
    # 阶段2：轮询等待并下载
    log_message("\n开始处理已提交的任务...", log_file, "INFO")
    if reached_limit:
        log_message("⚠ 已达到请求上限，只处理已提交的任务", log_file, "WARNING")
    
    await poll_task_statuses(
        notebook_id=notebook_id,
        tasks=tasks,
        check_status_func=check_ppt_status,
        check_all_statuses_func=check_all_ppt_statuses,
        download_func=download_ppt,
        output_dir=output_dir,
        log_file=log_file,
        max_check_rounds=MAX_CHECK_ROUNDS,
        check_interval=CHECK_INTERVAL
    )
    
    # 完成统计
    log_message("\n" + "=" * 70, log_file, "INFO")
    log_message("处理完成统计", log_file, "INFO")
    log_message("=" * 70, log_file, "INFO")
    
    final_completed = sum(1 for t in tasks if t.status == "completed")
    final_failed = sum(1 for t in tasks if t.status == "failed")
    total_tasks = len(tasks)
    success_rate = (final_completed / total_tasks * 100) if total_tasks > 0 else 0
    
    log_message(f"总计：{total_tasks}", log_file, "INFO")
    log_message(f"成功：{final_completed}", log_file, "INFO")
    log_message(f"失败：{final_failed}", log_file, "INFO")
    log_message(f"成功率：{success_rate:.1f}%", log_file, "INFO")
    log_message(f"输出目录：{output_dir}", log_file, "INFO")
    log_message(f"日志文件：{log_file}", log_file, "INFO")
    
    # 记录失败任务详情
    failed_tasks = [t for t in tasks if t.status == "failed"]
    if failed_tasks:
        log_message("\n失败任务详情:", log_file, "WARNING")
        for task in failed_tasks:
            log_message(f"  - {task.source_title}: {task.error_message or '未知错误'}", log_file, "WARNING")


async def main() -> None:
    """主函数"""
    print("=" * 60)
    print("NotebookLM PPT生成工具")
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
    notebooks: List[Dict[str, any]] = await list_notebooks()
    
    if not notebooks:
        print("✗ 没有找到笔记本")
        return
    
    print("\n可用笔记本:")
    for i, nb in enumerate(notebooks, 1):
        owner: str = "Owner" if nb["is_owner"] else "Shared"
        created: str = nb["created_at"][:10] if nb["created_at"] else "-"
        print(f"  {i}. {nb['title']}")
        print(f"     ID: {nb['id']}")
        print(f"     Owner: {owner}, Created: {created}")
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
    
    print(f"\n✓ 已选择笔记本: {notebook_name}")
    
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
        print(f"     类型: {source['type']}, 状态: {source['status']}")
        print()
    
    # 选择处理方式
    print("\n[步骤 4] 选择处理方式:")
    print("  1. 处理所有源文件")
    print("  2. 选择特定源文件（输入编号，多个用逗号分隔，支持范围格式如 2-5）")
    print("  3. 跳过已处理的源文件（输入编号，多个用逗号分隔，支持范围格式如 2-5）")
    
    while True:
        choice = input("\n请输入选项 (1/2/3) [默认: 1]: ").strip() or "1"
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
                print(f"✗ 发生错误: {e}")
                
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
                print(f"✗ 发生错误: {e}")
    
    # 过滤未就绪的源文件
    ready_sources = [s for s in selected_sources if s["status"] == SourceStatus.READY]
    skipped_sources = [s for s in selected_sources if s["status"] != SourceStatus.READY]
    
    if skipped_sources:
        print(f"\n⚠ 跳过 {len(skipped_sources)} 个未就绪的源文件")
    
    if not ready_sources:
        print("✗ 没有就绪的源文件可以处理")
        return
    
    print(f"✓ 将处理 {len(ready_sources)} 个就绪的源文件")
    
    # 配置PPT生成参数
    print("\n[步骤 5] 配置PPT生成参数")
    
    ppt_format = get_ppt_format_choice()
    print(f"✓ PPT格式: {ppt_format}")
    
    ppt_length = get_ppt_length_choice()
    print(f"✓ PPT长度: {ppt_length}")
    
    language = get_language_choice()
    print(f"✓ 语言: {language}")
    
    instructions = get_instructions(DEFAULT_INSTRUCTIONS)
    print(f"✓ 生成提示词: {instructions}")
    
    # 创建输出目录
    print(f"\n[步骤 6] 创建输出目录...")
    safe_notebook_name = sanitize_filename(notebook_name)
    output_dir = Path("./output") / f"{safe_notebook_name}_ppts"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"✓ 输出目录: {output_dir}")
    
    # 检查已存在的 PPT 文件
    print(f"\n[步骤 7] 检查已存在的 PPT 文件...")
    existing_count = 0
    sources_to_process = []
    
    for source in ready_sources:
        safe_title = sanitize_filename(Path(source["title"]).stem)
        output_filename = f"{safe_title}_slides.pdf"
        output_path = output_dir / output_filename
        
        if output_path.exists():
            print(f"  ⊘ 跳过已存在: {source['title']}")
            existing_count += 1
        else:
            sources_to_process.append(source)
    
    if existing_count > 0:
        print(f"\n✓ 已跳过 {existing_count} 个已存在的 PPT")
    
    if not sources_to_process:
        print("\n✓ 所有 PPT 都已存在，无需重新生成")
        return
    
    print(f"✓ 将为 {len(sources_to_process)} 个源文件生成 PPT")
    
    # 创建日志文件
    log_file = output_dir / "ppt_generation.log"
    log_message("=" * 60, log_file, "INFO")
    log_message("开始PPT生成任务", log_file, "INFO")
    log_message(f"笔记本: {notebook_name} ({notebook_id})", log_file, "INFO")
    log_message(f"PPT格式: {ppt_format}", log_file, "INFO")
    log_message(f"PPT长度: {ppt_length}", log_file, "INFO")
    log_message(f"语言: {language}", log_file, "INFO")
    log_message(f"提示词: {instructions}", log_file, "INFO")
    log_message(f"源文件数量: {len(sources_to_process)}", log_file, "INFO")
    log_message("=" * 60, log_file, "INFO")
    
    # 创建任务列表
    tasks = []
    for s in sources_to_process:
        safe_title = sanitize_filename(Path(s["title"]).stem)
        task = PPTGenerationTask(
            source_id=s["id"],
            source_title=s["title"],
            output_filename=f"{safe_title}_slides.pdf"
        )
        tasks.append(task)
    
    # 处理PPT生成
    print(f"\n[步骤 8] 开始批量生成PPT...")
    print("=" * 60)
    
    await process_ppt_batch(
        notebook_id=notebook_id,
        notebook_name=notebook_name,
        tasks=tasks,
        ppt_format=ppt_format,
        ppt_length=ppt_length,
        language=language,
        instructions=instructions,
        output_dir=output_dir,
        log_file=log_file
    )
    
    # 完成
    print("\n" + "=" * 60)
    print("✓ 所有任务处理完成!")
    print(f"  输出目录: {output_dir}")
    print(f"  日志文件: {log_file}")
    
    # 显示失败任务
    failed_tasks = [t for t in tasks if t.status == "failed"]
    if failed_tasks:
        print(f"\n⚠ 失败任务 ({len(failed_tasks)}个):")
        for t in failed_tasks:
            print(f"  - {t.source_title}: {t.error_message or '未知错误'}")


if __name__ == "__main__":
    asyncio.run(main())