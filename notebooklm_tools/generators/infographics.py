#!/usr/bin/env python3
"""
NotebookLM 信息图生成脚本

功能：为 NotebookLM 笔记本中的源文件批量生成信息图，并自动下载
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
from ..cli import get_user_choice, get_language_choice, get_instructions


# 配置常量
MAX_CHECK_ROUNDS = 20  # 最多等待20分钟
CHECK_INTERVAL = 60  # 检查间隔（秒）
DEFAULT_INSTRUCTIONS = "手绘风格"


# 映射字典
ORIENTATION_MAP = {
    "1": "landscape",
    "2": "portrait",
    "3": "square"
}

DETAIL_MAP = {
    "1": "standard",
    "2": "concise",
    "3": "detailed"
}

STYLE_MAP = {
    "1": "sketch-note",
    "2": "auto",
    "3": "professional",
    "4": "bento-grid",
    "5": "editorial",
    "6": "instructional",
    "7": "bricks",
    "8": "clay",
    "9": "anime",
    "10": "kawaii",
    "11": "scientific"
}


@dataclass
class InfographicGenerationTask(BaseGenerationTask):
    """信息图生成任务"""
    pass


async def submit_infographic_generation(
    notebook_id: str,
    source_id: str,
    orientation: str,
    detail: str,
    style: str,
    language: str,
    instructions: str
) -> str:
    """
    提交信息图生成任务
    
    Returns:
        artifact_id: 生成的 artifact ID
    """
    try:
        # 转义指令中的引号，避免命令执行错误
        escaped_instructions = instructions.replace('"', '\\"') if instructions else ""
        cmd = f'notebooklm generate infographic --notebook {notebook_id} --source {source_id} --orientation {orientation} --detail {detail} --style {style} --language {language} "{escaped_instructions}" --json'
        
        code, stdout, stderr = run_command(cmd)
        
        if code != 0:
            raise Exception(f"提交信息图生成失败: {stderr}")
        
        try:
            result = json.loads(stdout)
            if "task_id" in result:
                return result["task_id"]
            elif "error" in result:
                raise Exception(f"API错误: {result['error']}")
            else:
                raise Exception("未找到 task_id")
        except json.JSONDecodeError:
            raise Exception(f"解析JSON失败: {stdout}")
    except Exception as e:
        raise Exception(f"提交信息图生成任务失败: {str(e)}")


async def check_all_infographic_statuses(notebook_id: str) -> Dict[str, dict]:
    """
    批量检查所有信息图状态
    
    Returns:
        dict: artifact_id -> status_info
    """
    cmd = f'notebooklm artifact list --notebook {notebook_id} --type infographic --json'
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


async def check_infographic_status(notebook_id: str, artifact_id: str) -> Optional[dict]:
    """
    检查单个信息图生成状态
    
    Returns:
        dict with keys: status (str), is_complete (bool), is_failed (bool)
    """
    status_map = await check_all_infographic_statuses(notebook_id)
    return status_map.get(artifact_id)


async def download_infographic(
    notebook_id: str,
    artifact_id: str,
    output_path: Path
) -> bool:
    """
    下载信息图
    
    Returns:
        bool: 是否成功
    """
    try:
        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        cmd = f'notebooklm download infographic --notebook {notebook_id} -a {artifact_id} "{str(output_path)}" --force'
        code, stdout, stderr = run_command(cmd)
        
        if code == 0:
            return True
        else:
            print(f"下载失败: {stderr}")
            return False
    except Exception as e:
        print(f"下载信息图时出错: {str(e)}")
        return False


def get_orientation_choice() -> str:
    """获取方向选择"""
    options = [
        ("landscape", "横向 (默认)"),
        ("portrait", "纵向"),
        ("square", "方形")
    ]
    
    choice = get_user_choice("方向选择", options, "1")
    return ORIENTATION_MAP.get(choice, "landscape")


def get_detail_choice() -> str:
    """获取详细程度选择"""
    options = [
        ("standard", "标准 (默认)"),
        ("concise", "简洁"),
        ("detailed", "详细")
    ]
    
    choice = get_user_choice("详细程度选择", options, "1")
    return DETAIL_MAP.get(choice, "standard")


def get_style_choice() -> str:
    """获取风格选择"""
    options = [
        ("sketch-note", "素描笔记风格 (默认)"),
        ("auto", "自动选择"),
        ("professional", "专业风格"),
        ("bento-grid", "便当网格风格"),
        ("editorial", "编辑风格"),
        ("instructional", "教学风格"),
        ("bricks", "砖块风格"),
        ("clay", "黏土风格"),
        ("anime", "动画风格"),
        ("kawaii", "可爱风格"),
        ("scientific", "科学风格")
    ]
    
    choice = get_user_choice("风格选择", options, "1")
    return STYLE_MAP.get(choice, "sketch-note")


async def process_infographic_batch(
    notebook_id: str,
    notebook_name: str,
    tasks: List[InfographicGenerationTask],
    orientation: str,
    detail: str,
    style: str,
    language: str,
    instructions: str,
    output_dir: Path,
    log_file: Path
):
    """
    批量处理信息图生成任务
    
    策略：
    1. 先依次提交所有生成任务
    2. 如果达到请求上限，停止提交
    3. 然后轮询检查状态，每1分钟检查一次
    4. 完成的立即下载
    """
    # 阶段1：提交所有生成任务
    async def submit_func(notebook_id, source_id, task):
        artifact_id = await submit_infographic_generation(
            notebook_id=notebook_id,
            source_id=source_id,
            orientation=orientation,
            detail=detail,
            style=style,
            language=language,
            instructions=instructions
        )
        # 生成输出文件名
        safe_title = sanitize_filename(Path(task.source_title).stem)
        task.output_filename = f"{safe_title}.png"
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
        check_status_func=check_infographic_status,
        check_all_statuses_func=check_all_infographic_statuses,
        download_func=download_infographic,
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
    
    log_message(f"总计: {total_tasks}", log_file, "INFO")
    log_message(f"成功: {final_completed}", log_file, "INFO")
    log_message(f"失败: {final_failed}", log_file, "INFO")
    log_message(f"成功率: {success_rate:.1f}%", log_file, "INFO")
    log_message(f"输出目录: {output_dir}", log_file, "INFO")
    log_message(f"日志文件: {log_file}", log_file, "INFO")
    
    # 记录失败任务详情
    failed_tasks = [t for t in tasks if t.status == "failed"]
    if failed_tasks:
        log_message("\n失败任务详情:", log_file, "WARNING")
        for task in failed_tasks:
            log_message(f"  - {task.source_title}: {task.error_message or '未知错误'}", log_file, "WARNING")


async def main():
    """主函数"""
    print("=" * 70)
    print("NotebookLM 信息图生成工具")
    print("=" * 70)
    
    # 检查登录状态
    print("\n[步骤 1] 检查登录状态...")
    if not await check_login_status():
        print("✗ 未登录，请先运行: notebooklm login")
        print("  提示: 运行 'notebooklm login' 命令进行登录")
        return
    print("✓ 已登录")
    
    # 列出笔记本
    print("\n[步骤 2] 列出所有笔记本...")
    notebooks = await list_notebooks()
    
    if not notebooks:
        print("✗ 没有找到笔记本")
        print("  提示: 请先在 NotebookLM 中创建笔记本并添加源文件")
        return
    
    print("\n可用笔记本:")
    for i, nb in enumerate(notebooks, 1):
        owner = "Owner" if nb["is_owner"] else "Shared"
        created = nb["created_at"][:10] if nb["created_at"] else "-"
        print(f"  {i}. {nb['title']}")
        print(f"     ID: {nb['id']}")
        print(f"     类型: {owner}, 创建时间: {created}")
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
        print("  提示: 请先在 NotebookLM 中为笔记本添加源文件")
        return
    
    print(f"\n找到 {len(sources)} 个源文件:")
    for i, source in enumerate(sources, 1):
        status_icon = "✓" if source["status"] == SourceStatus.READY else "⊘"
        status_text = "就绪" if source["status"] == SourceStatus.READY else "未就绪"
        print(f"  {i}. {status_icon} {source['title']}")
        print(f"     类型: {source['type']}, 状态: {status_text}")
        print()
    
    # 选择处理方式
    print("\n[步骤 4] 选择处理方式:")
    print("  1. 处理所有源文件")
    print("  2. 选择特定源文件（输入编号，多个用逗号分隔）")
    print("  3. 跳过已处理的源文件（输入编号，多个用逗号分隔）")
    
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
        print("  提示: 只有状态为 'READY' 的源文件才能生成信息图")
    
    if not ready_sources:
        print("✗ 没有就绪的源文件可以处理")
        print("  提示: 请等待源文件处理完成后再尝试")
        return
    
    print(f"✓ 将处理 {len(ready_sources)} 个就绪的源文件")
    
    # 配置信息图生成参数
    print("\n[步骤 5] 配置信息图生成参数")
    
    orientation = get_orientation_choice()
    print(f"✓ 方向: {orientation}")
    
    detail = get_detail_choice()
    print(f"✓ 详细程度: {detail}")
    
    style = get_style_choice()
    print(f"✓ 风格: {style}")
    
    language = get_language_choice()
    print(f"✓ 语言: {language}")
    
    instructions = get_instructions(DEFAULT_INSTRUCTIONS)
    print(f"✓ 生成指令: {instructions}")
    
    # 创建输出目录
    print(f"\n[步骤 6] 创建输出目录...")
    safe_notebook_name = sanitize_filename(notebook_name)
    output_dir = Path("./output") / f"{safe_notebook_name}_infographics"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"✓ 输出目录: {output_dir}")
    except Exception as e:
        print(f"✗ 创建输出目录失败: {e}")
        return
    
    # 创建日志文件
    log_file = output_dir / "infographic_generation.log"
    log_message("=" * 70, log_file, "INFO")
    log_message("开始信息图生成任务", log_file, "INFO")
    log_message(f"笔记本: {notebook_name} ({notebook_id})", log_file, "INFO")
    log_message(f"方向: {orientation}", log_file, "INFO")
    log_message(f"详细程度: {detail}", log_file, "INFO")
    log_message(f"风格: {style}", log_file, "INFO")
    log_message(f"语言: {language}", log_file, "INFO")
    log_message(f"提示词: {instructions}", log_file, "INFO")
    log_message(f"源文件数量: {len(ready_sources)}", log_file, "INFO")
    log_message("=" * 70, log_file, "INFO")
    
    # 创建任务列表
    tasks = [
        InfographicGenerationTask(source_id=s["id"], source_title=s["title"])
        for s in ready_sources
    ]
    
    # 处理信息图生成
    print(f"\n[步骤 7] 开始批量生成信息图...")
    print("=" * 70)
    print(f"将为 {len(tasks)} 个源文件生成信息图")
    print(f"预计总耗时: 约 {len(tasks) * 5} 分钟")
    print("=" * 70)
    
    await process_infographic_batch(
        notebook_id=notebook_id,
        notebook_name=notebook_name,
        tasks=tasks,
        orientation=orientation,
        detail=detail,
        style=style,
        language=language,
        instructions=instructions,
        output_dir=output_dir,
        log_file=log_file
    )
    
    # 完成
    print("\n" + "=" * 70)
    print("✓ 所有任务处理完成!")
    print(f"  输出目录: {output_dir}")
    print(f"  日志文件: {log_file}")
    print("=" * 70)
    
    # 显示失败任务
    failed_tasks = [t for t in tasks if t.status == "failed"]
    if failed_tasks:
        print(f"\n⚠ 失败任务 ({len(failed_tasks)}个):")
        print("  " + "-" * 50)
        for t in failed_tasks:
            error_msg = t.error_message or "未知错误"
            print(f"  - {t.source_title}")
            print(f"    错误: {error_msg}")
        print("  " + "-" * 50)
        print("  提示: 请查看日志文件获取详细错误信息")
    
    # 显示成功任务
    completed_tasks = [t for t in tasks if t.status == "completed"]
    if completed_tasks:
        print(f"\n✓ 成功任务 ({len(completed_tasks)}个):")
        print("  " + "-" * 50)
        for t in completed_tasks[:5]:  # 只显示前5个，避免输出过多
            print(f"  - {t.source_title}")
        if len(completed_tasks) > 5:
            print(f"  ... 还有 {len(completed_tasks) - 5} 个成功任务")
        print("  " + "-" * 50)
    
    print("\n感谢使用 NotebookLM 信息图生成工具!")


if __name__ == "__main__":
    asyncio.run(main())