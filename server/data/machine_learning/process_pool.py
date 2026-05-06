import os
from concurrent.futures import Future, ProcessPoolExecutor
from typing import Any, Dict, Optional, Sequence, Union

from server.data.machine_learning.machine_learning_model import train_model_once

# === 多进程训练任务提交 ===

_TRAIN_EXECUTOR: Optional[ProcessPoolExecutor] = None


def get_train_executor(max_workers: Optional[int] = None) -> ProcessPoolExecutor:
    """
    获取全局模型训练进程池。
    """
    global _TRAIN_EXECUTOR
    if _TRAIN_EXECUTOR is None:
        if max_workers is None:
            max_workers = max(os.cpu_count() or 2, 2)
        _TRAIN_EXECUTOR = ProcessPoolExecutor(max_workers=max_workers)
    return _TRAIN_EXECUTOR


def submit_train_task(
    user_id: Union[int, str],
    model_name: str,
    X_columns: Sequence[str],
    y_column: Union[str, Sequence[str]],
    mode: str,
    model_param: Optional[Dict[str, Any]] = None,
    test_size: float = 0.2,
    random_state: int = 42,
    use_bayes_search: bool = False,
    bayes_iter: int = 5,
    save_dir: str = "./user_cache/ml_models",
    save_model: bool = True,
    max_workers: Optional[int] = None,
) -> Future:
    """
    将训练任务提交到多进程池中执行，返回 Future。

    适用于分钟级训练任务，由调用方决定是同步等待 result() 还是异步集成。
    """
    executor = get_train_executor(max_workers=max_workers)
    return executor.submit(
        train_model_once,
        user_id,
        model_name,
        X_columns,
        y_column,
        mode,
        model_param,
        test_size,
        random_state,
        use_bayes_search,
        bayes_iter,
        save_dir,
        save_model,
    )


def shutdown_train_executor(wait: bool = True) -> None:
    """
    关闭全局训练进程池（通常只在进程退出前调用一次）。
    """
    global _TRAIN_EXECUTOR
    if _TRAIN_EXECUTOR is not None:
        _TRAIN_EXECUTOR.shutdown(wait=wait)
        _TRAIN_EXECUTOR = None

