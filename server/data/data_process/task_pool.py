
import os
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")

_executor: Optional[ThreadPoolExecutor] = None


def get_executor(max_workers: Optional[int] = None) -> ThreadPoolExecutor:
    """
    获取/创建全局线程池实例。

    :param max_workers: 最大工作线程数，仅第一次创建线程池时生效。
                        默认为 CPU 核心数。
    """
    global _executor
    if _executor is None:
        if max_workers is None:
            max_workers = os.cpu_count() or 4
        _executor = ThreadPoolExecutor(max_workers=max_workers)
    return _executor


def submit_task(
    func: Callable[..., T],
    /,
    *args: Any,
    max_workers: Optional[int] = None,
    **kwargs: Any,
) -> Future:
    """
    提交任意函数到全局线程池执行。

    用法示例：
        future = submit_task(some_func, arg1, arg2, kw1=..., kw2=...)
        result = future.result()

    :param func: 要在线程池中执行的函数（任意可调用对象）
    :param args: 传给函数的位置参数
    :param max_workers: 最大工作线程数，仅第一次创建线程池时生效
    :param kwargs: 传给函数的关键字参数
    :return: concurrent.futures.Future[T]
    """
    executor = get_executor(max_workers=max_workers)
    return executor.submit(func, *args, **kwargs)


def shutdown(wait: bool = True) -> None:
    """
    关闭全局线程池（一般在进程退出前调用一次即可）。
    """
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=wait)
        _executor = None

