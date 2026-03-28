#!/usr/bin/env python3
"""
Task management for NotebookLM generation tasks
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any, Callable
from pathlib import Path

from .utils import run_command, log_message, sanitize_filename


@dataclass
class BaseGenerationTask:
    """基础生成任务"""
    source_id: str
    source_title: str
    artifact_id: Optional[str] = None
    status: str = "pending"  # pending, generating, completed, failed
    output_filename: Optional[str] = None
    error_message: Optional[str] = None
    skipped: bool = False  # 是否因文件已存在而跳过
    download_retry_count: int = 0  # 下载重试次数


async def submit_generation_tasks(
    notebook_id: str,
    tasks: List[BaseGenerationTask],
    submit_func: Callable[[str, str, Any], str],
    log_file: Path
) -> Tuple[int, bool]:
    """提交所有生成任务
    
    Args:
        notebook_id: 笔记本ID
        tasks: 任务列表
        submit_func: 提交单个任务的函数
        log_file: 日志文件路径
    
    Returns:
        Tuple[int, bool]: (成功提交的任务数, 是否达到请求上限)
    """
    log_message("=" * 70, log_file)
    log_message("阶段1: 提交生成任务", log_file)
    log_message(f"任务总数: {len(tasks)}", log_file)
    log_message("=" * 70, log_file)
    
    submitted_count: int = 0
    total_tasks: int = len(tasks)
    reached_limit: bool = False
    
    # 检测请求上限的关键词
    limit_keywords = ["limit", "quota", "上限", "超出", "exceeded", "maximum", "CREATE_ARTIFACT"]
    
    for i, task in enumerate(tasks, 1):
        # 如果已经达到请求上限，停止提交
        if reached_limit:
            task.status = "failed"
            task.error_message = "已达到每日请求上限，停止提交"
            log_message(f"✗ 已达到请求上限，跳过: {task.source_title}", log_file, "WARNING")
            continue
        
        print(f"\n[{i}/{total_tasks}] 提交: {task.source_title}")
        
        try:
            artifact_id: str = await submit_func(notebook_id, task.source_id, task)
            
            task.artifact_id = artifact_id
            task.status = "generating"
            
            log_message(f"✓ 已提交: {task.source_title} -> artifact_id: {artifact_id}", log_file, "INFO")
            submitted_count += 1
            
        except Exception as e:
            error_msg = str(e).lower()
            task.status = "failed"
            task.error_message = str(e)
            
            # 检查是否是请求上限错误
            if any(keyword in error_msg for keyword in limit_keywords):
                reached_limit = True
                log_message(f"✗ 达到请求上限: {task.source_title} - {e}", log_file, "ERROR")
                log_message("⚠ 已达到每日请求上限，停止提交后续任务", log_file, "WARNING")
            else:
                log_message(f"✗ 提交失败: {task.source_title} - {e}", log_file, "ERROR")
        
        # 提交间隔，避免请求过快
        await asyncio.sleep(1)
    
    failed_count: int = total_tasks - submitted_count
    log_message(f"\n提交完成: 成功 {submitted_count}, 失败 {failed_count}", log_file, "INFO")
    log_message(f"提交成功率: {submitted_count / total_tasks * 100:.1f}%", log_file, "INFO")
    if reached_limit:
        log_message("⚠ 注意: 已达到每日请求上限", log_file, "WARNING")
    
    return submitted_count, reached_limit


async def poll_task_statuses(
    notebook_id: str,
    tasks: List[BaseGenerationTask],
    check_status_func: Callable[[str, str], Optional[Dict]],
    check_all_statuses_func: Callable[[str], Dict[str, Dict]],
    download_func: Callable[[str, str, Path], bool],
    output_dir: Path,
    log_file: Path,
    max_check_rounds: int = 20,
    check_interval: int = 60
):
    """轮询任务状态
    
    Args:
        notebook_id: 笔记本ID
        tasks: 任务列表
        check_status_func: 检查单个任务状态的函数
        check_all_statuses_func: 批量检查所有任务状态的函数
        download_func: 下载完成任务的函数
        output_dir: 输出目录
        log_file: 日志文件路径
        max_check_rounds: 最大检查轮数
        check_interval: 检查间隔（秒）
    """
    log_message("\n" + "=" * 60, log_file)
    log_message("阶段2: 等待生成完成并下载", log_file, "INFO")
    log_message("=" * 60, log_file)
    log_message(f"生成通常需要几分钟，将每{check_interval}秒检查一次状态\n", log_file, "INFO")
    
    pending_tasks = [t for t in tasks if t.status == "generating"]
    completed_count = 0
    failed_count = 0
    check_round = 0
    total_tasks = len(pending_tasks)
    
    print(f"\n开始监控 {total_tasks} 个生成任务...")
    print("=" * 60)
    
    while pending_tasks and check_round < max_check_rounds:
        check_round += 1
        
        still_pending = []
        completed_tasks = []
        newly_completed = 0
        newly_failed = 0
        
        try:
            # 批量检查所有任务状态，减少API调用
            status_map = await check_all_statuses_func(notebook_id)
            
            for task in pending_tasks:
                if not task.artifact_id:
                    still_pending.append(task)
                    continue
                
                status_info = status_map.get(task.artifact_id)
                
                if not status_info:
                    still_pending.append(task)
                    continue
                
                if status_info["is_complete"]:
                    # 任务已完成，加入待下载列表
                    completed_tasks.append(task)
                    newly_completed += 1
                    print(f"  ✓ {task.source_title} - 生成完成")
                    
                elif status_info["is_failed"]:
                    task.status = "failed"
                    task.error_message = f"生成失败: {status_info['status']}"
                    failed_count += 1
                    newly_failed += 1
                    print(f"  ✗ {task.source_title} - 生成失败: {status_info['status']}")
                    log_message(f"✗ 生成失败: {task.source_title} - {status_info['status']}", log_file, "ERROR")
                    
                else:
                    # 仍在生成中
                    still_pending.append(task)
                    
        except Exception as e:
            # 如果批量检查失败，回退到单个检查
            log_message(f"⚠ 批量检查状态失败，回退到单个检查: {e}", log_file, "WARNING")
            print(f"  ⚠ 批量检查状态失败，回退到单个检查")
            
            for task in pending_tasks:
                try:
                    status_info = await check_status_func(notebook_id, task.artifact_id)
                    
                    if not status_info:
                        still_pending.append(task)
                        continue
                    
                    if status_info["is_complete"]:
                        completed_tasks.append(task)
                        newly_completed += 1
                        print(f"  ✓ {task.source_title} - 生成完成")
                    elif status_info["is_failed"]:
                        task.status = "failed"
                        task.error_message = f"生成失败: {status_info['status']}"
                        failed_count += 1
                        newly_failed += 1
                        print(f"  ✗ {task.source_title} - 生成失败: {status_info['status']}")
                        log_message(f"✗ 生成失败: {task.source_title} - {status_info['status']}", log_file, "ERROR")
                    else:
                        still_pending.append(task)
                        
                except Exception as e:
                    still_pending.append(task)
                    log_message(f"⚠ 检查状态时出错: {task.source_title} - {e}", log_file, "WARNING")
        
        # 并发下载已完成的任务
        if completed_tasks:
            print(f"\n  开始下载 {len(completed_tasks)} 个已完成的任务...")
            
            async def download_task(task: BaseGenerationTask) -> Tuple[bool, bool]:
                """
                下载任务
                Returns:
                    Tuple[是否成功，是否应该重新尝试下载]
                """
                output_path: Path = output_dir / task.output_filename
                success: bool = await download_func(
                    notebook_id=notebook_id,
                    artifact_id=task.artifact_id,
                    output_path=output_path
                )
                
                if success:
                    task.status = "completed"
                    log_message(f"✓ 下载成功：{task.output_filename}", log_file, "INFO")
                    return True, False
                else:
                    # 下载失败，但不是生成失败，可以重试
                    task.download_retry_count += 1
                    log_message(f"✗ 下载失败（第{task.download_retry_count}次）: {task.output_filename}", log_file, "WARNING")
                    # 返回失败，但可以重新尝试
                    return False, True
            
            download_tasks = [download_task(task) for task in completed_tasks]
            results = await asyncio.gather(*download_tasks, return_exceptions=True)
            
            download_success = 0
            tasks_to_retry = []
            
            for i, result in enumerate(results):
                if isinstance(result, tuple):
                    success, should_retry = result
                    if success:
                        download_success += 1
                    elif should_retry:
                        # 需要重试下载的任务，重新加入待处理队列
                        task = completed_tasks[i]
                        task.status = "generating"  # 恢复为 generating 状态，以便下次继续检查
                        tasks_to_retry.append(task)
                elif isinstance(result, Exception):
                    # 异常也视为需要重试
                    task = completed_tasks[i]
                    task.download_retry_count += 1
                    log_message(f"✗ 下载异常（第{task.download_retry_count}次）: {task.source_title} - {result}", log_file, "WARNING")
                    task.status = "generating"
                    tasks_to_retry.append(task)
            
            completed_count += download_success
            failed_count += len(completed_tasks) - download_success - len(tasks_to_retry)
            
            # 将需要重试的任务加回待处理队列
            still_pending.extend(tasks_to_retry)
            
            if tasks_to_retry:
                print(f"  下载完成：成功 {download_success}, 失败 {len(completed_tasks) - download_success}（{len(tasks_to_retry)} 个将重试下载）")
            else:
                print(f"  下载完成：成功 {download_success}, 失败 {len(completed_tasks) - download_success}")
        
        pending_tasks = still_pending
        
        # 显示进度
        print(f"\n第{check_round}次检测: 共{total_tasks}需要下载，已下载{completed_count}，生成失败{failed_count}")
        print(f"  剩余任务: {len(pending_tasks)}，预计剩余时间: {max(0, max_check_rounds - check_round)}分钟")
        print("=" * 60)
        
        if pending_tasks and check_round < max_check_rounds:
            print(f"  等待 {check_interval} 秒后再次检查...")
            await asyncio.sleep(check_interval)  # 等待指定间隔
    
    # 超时处理
    if pending_tasks:
        print(f"\n⚠ 超时（{max_check_rounds}分钟）: 以下任务仍在处理中")
        log_message(f"\n⚠ 超时（{max_check_rounds}分钟）: 以下任务仍在处理中", log_file, "WARNING")
        for task in pending_tasks:
            print(f"  - {task.source_title} (artifact_id: {task.artifact_id})")
            log_message(f"  - {task.source_title} (artifact_id: {task.artifact_id})", log_file, "WARNING")
            task.status = "failed"
            task.error_message = "生成超时"