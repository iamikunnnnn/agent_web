"""全局安装管理器 - 处理依赖安装和服务重启的协调"""

import asyncio
import fcntl
import logging
import os
import shlex
import shutil
import sys
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Dict, Optional


class InstallationStatus(str, Enum):
    IDLE = "idle"
    INSTALLING = "installing"
    RESTARTING = "restarting"
    READY = "ready"


class InstallationManager:
    """全局安装管理器 - 单例模式"""

    _instance: Optional['InstallationManager'] = None

    def __new__(cls):
        """
        作用：当无实例时创建一个InstallationManager类绑定到cls._instance，并在后续__init__中实例化
        当已存在实例时，确保如果多次实例化InstallationManager只会返回cls._instance，确保单例。
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._status: InstallationStatus = InstallationStatus.IDLE
        self._lock = asyncio.Lock()
        self._installing_packages: list[str] = []
        self._last_install_time: Optional[datetime] = None
        self._restart_task: Optional[asyncio.Task] = None
        self._logger = logging.getLogger(__name__)
        try:
            # 重启延迟
            self._restart_delay = float(os.getenv("AGNO_RESTART_DELAY_SECONDS", "2.0"))
        except ValueError:
            self._restart_delay = 2.0
        self._initialized = True
        # 文件锁配置（跨进程互斥）：默认启用
        self._use_file_lock: bool = os.getenv("AGNO_INSTALL_LOCK", "true").lower() == "true"
        self._lock_file_path: str = os.getenv(
            "AGNO_INSTALL_LOCK_PATH",
            os.path.join(os.getcwd(), "tmp", "install.lock")
        )
        self._lock_fp: Optional[Any] = None

    @property
    def status(self) -> InstallationStatus:
        """获取当前状态"""
        return self._status

    @property
    def is_busy(self) -> bool:
        """是否正在安装或重启"""
        # 简化后端状态机，不再对外报告忙碌，交由前端禁用按钮控制
        return False

    @property
    def installing_packages(self) -> list[str]:
        """当前正在安装的包列表"""
        return self._installing_packages.copy()

    async def install_package(
            self,
            package_name: str,
            install_command: str,
            auto_restart: bool = True
    ) -> Dict[str, Any]:
        """
        安装包并可选地触发重启

        Args:
            package_name: 包名
            install_command: 安装命令
            auto_restart: 是否自动触发重启

        Returns:
            安装结果字典
        """
        # 先尝试获取文件锁（非阻塞）以防止跨进程并发安装
        if self._use_file_lock and not self._try_acquire_file_lock():
            return {
                "success": False,
                "package": package_name,
                "message": "已有依赖安装在进行中，请稍后重试"
            }

        async with self._lock:
            try:
                self._installing_packages.append(package_name)
                self._last_install_time = datetime.now()

                # 执行安装
                cmd_parts = shlex.split(install_command)

                process = await asyncio.create_subprocess_exec(
                    *cmd_parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=os.getcwd()
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=300  # 5分钟超时
                )

                success = process.returncode == 0

                result = {
                    "success": success,
                    "package": package_name,
                    "message": "安装成功" if success else f"安装失败: {stderr.decode()[:200]}",
                    "stdout": stdout.decode()[:500] if stdout else "",
                    "stderr": stderr.decode()[:500] if stderr else "",
                }

                # 如果安装成功且需要重启，则调度一次进程重启
                if success and auto_restart:
                    self._schedule_restart()
                    result["restart_scheduled"] = True
                    result["restart_in_seconds"] = self._restart_delay

                return result

            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "package": package_name,
                    "message": "安装超时(>5分钟)"
                }
            except Exception as e:
                return {
                    "success": False,
                    "package": package_name,
                    "message": f"安装错误: {str(e)}"
                }
            finally:
                # 清理状态
                if package_name in self._installing_packages:
                    self._installing_packages.remove(package_name)
                # 不再维护 RESTARTING/IDLE 状态机，交由前端控制交互
                # 释放文件锁
                self._release_file_lock()

    # 提示: 当前运行在非 --reload 模式，需要依赖本类调度的手动重启

    async def install_package_stream(
            self,
            package_name: str,
            install_command: str,
            auto_restart: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        流式安装包，实时返回日志

        Args:
            package_name: 包名
            install_command: 安装命令
            auto_restart: 是否自动触发重启

        Yields:
            日志行 (JSON 格式)
        """
        import json

        # 先尝试获取文件锁（非阻塞）以防止跨进程并发安装
        if self._use_file_lock and not self._try_acquire_file_lock():
            # 输出一个 start 行，以便前端创建日志 toast
            yield json.dumps({
                "type": "start",
                "message": f"准备安装 {package_name}...",
                "package": package_name,
                "command": install_command
            }) + "\n"
            # 再输出错误行，提示当前已有安装在进行中
            yield json.dumps({
                "type": "error",
                "message": "已有依赖安装在进行中，请稍后重试"
            }) + "\n"
            # 结束
            yield json.dumps({"type": "done"}) + "\n"
            return

        async with self._lock:
            try:
                self._installing_packages.append(package_name)
                self._last_install_time = datetime.now()

                yield json.dumps({
                    "type": "start",
                    "message": f"开始安装 {package_name}...",
                    "package": package_name,
                    "command": install_command
                }) + "\n"

                # 执行安装
                cmd_parts = shlex.split(install_command)

                process = await asyncio.create_subprocess_exec(
                    *cmd_parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,  # 合并 stderr 到 stdout
                    cwd=os.getcwd()
                )

                # 实时读取输出
                assert process.stdout is not None
                async for line in process.stdout:
                    decoded_line = line.decode('utf-8', errors='replace').rstrip()
                    if decoded_line:  # 过滤空行
                        yield json.dumps({
                            "type": "log",
                            "message": decoded_line
                        }) + "\n"

                await process.wait()
                success = process.returncode == 0

                if success:
                    yield json.dumps({
                        "type": "success",
                        "message": f"{package_name} 安装成功",
                        "package": package_name
                    }) + "\n"

                    # 如果需要重启，调度一次任务，稍后执行 os.execv
                    if auto_restart:
                        self._schedule_restart()
                        yield json.dumps({
                            "type": "restart",
                            "message": f"依赖安装成功，服务将在 {self._restart_delay:.1f}s 后自动重启",
                            "restart_triggered": True
                        }) + "\n"
                        # 先发送 done 消息，让前端正常关闭流
                        yield json.dumps({"type": "done"}) + "\n"
                        return
                else:
                    yield json.dumps({
                        "type": "error",
                        "message": f"{package_name} 安装失败 (返回码: {process.returncode})"
                    }) + "\n"

                # 只在没有重启的情况下发送 done
                if not (success and auto_restart):
                    yield json.dumps({"type": "done"}) + "\n"

            except asyncio.TimeoutError:
                yield json.dumps({
                    "type": "error",
                    "message": "安装超时(>5分钟)"
                }) + "\n"
            except Exception as e:
                yield json.dumps({
                    "type": "error",
                    "message": f"安装错误: {str(e)}"
                }) + "\n"
            finally:
                # 清理状态
                if package_name in self._installing_packages:
                    self._installing_packages.remove(package_name)
                # 释放文件锁
                self._release_file_lock()

    def get_status_info(self) -> Dict[str, Any]:
        """获取详细状态信息"""
        return {
            "status": self._status.value,
            "is_busy": self._status != InstallationStatus.IDLE,
            "installing_packages": self.installing_packages,
            "restart_scheduled": bool(self._restart_task and not self._restart_task.done()),
            "last_install_time": self._last_install_time.isoformat() if self._last_install_time else None,
        }

    def _try_acquire_file_lock(self) -> bool:
        """尝试获取跨进程文件锁（非阻塞）。成功返回 True，失败返回 False。"""
        try:
            os.makedirs(os.path.dirname(self._lock_file_path), exist_ok=True)
            # 以追加模式打开锁文件，避免清空内容
            self._lock_fp = open(self._lock_file_path, "a+")
            fcntl.flock(self._lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            # 已被其他进程持有
            return False
        except Exception:
            # 若锁机制不可用或异常，降级为允许安装（不阻塞）
            return True

    def _release_file_lock(self) -> None:
        """释放文件锁"""
        try:
            if self._lock_fp is not None:
                try:
                    fcntl.flock(self._lock_fp, fcntl.LOCK_UN)
                except Exception:
                    pass
                try:
                    self._lock_fp.close()
                except Exception:
                    pass
                self._lock_fp = None
        except Exception:
            pass

    # 以下为自动重启的调度与执行逻辑
    def _schedule_restart(self, delay_seconds: Optional[float] = None) -> None:
        """调度一次延迟重启，避免重复触发"""
        delay = delay_seconds if delay_seconds is not None else self._restart_delay
        if delay < 0:
            delay = 0

        if self._restart_task and not self._restart_task.done():
            self._logger.info("已有重启任务排队，跳过新的调度")
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._logger.error("当前上下文没有运行中的事件循环，无法自动重启")
            return

        self._logger.info("依赖安装完成，将在 %.1fs 后自动重启服务", delay)
        self._restart_task = loop.create_task(self._restart_after_delay(delay))

    async def _restart_after_delay(self, delay_seconds: float) -> None:
        """等待一段时间，确保响应返回后再执行重启"""
        self._status = InstallationStatus.RESTARTING
        try:
            await asyncio.sleep(max(0.1, delay_seconds))
        except asyncio.CancelledError:
            self._logger.info("重启任务被取消")
            self._status = InstallationStatus.IDLE
            return
        self._perform_exec_restart()

    def _perform_exec_restart(self) -> None:
        """调用 os.execv 重新加载当前进程"""
        exec_path, args = self._resolve_restart_command()
        if not exec_path or not args:
            self._logger.error("无法解析重启命令，自动重启失败，请手动重启服务")
            self._status = InstallationStatus.IDLE
            self._restart_task = None
            return

        self._logger.info("执行自动重启: %s", " ".join(args))
        # 确保文件锁释放
        self._release_file_lock()
        try:
            os.execv(exec_path, args)
        except Exception:
            self._logger.exception("自动重启失败，进程将直接退出")
            os._exit(1)

    def _resolve_restart_command(self) -> tuple[Optional[str], Optional[list[str]]]:
        """推断用于重启当前服务的命令"""
        restart_cmd = os.getenv("AGNO_MANUAL_RESTART_CMD")
        if restart_cmd:
            parts = shlex.split(restart_cmd)
            if not parts:
                return None, None
            exec_path = shutil.which(parts[0]) or os.path.abspath(parts[0])
            return exec_path, parts

        argv = sys.argv or []
        if not argv:
            return sys.executable, [sys.executable]

        argv0 = argv[0]
        # 如果是直接运行的 Python 脚本
        if argv0.endswith((".py", ".pyc", ".pyw")) or argv0 == "__main__.py":
            script_path = argv0 if os.path.isabs(argv0) else os.path.abspath(argv0)
            return sys.executable, [sys.executable, script_path, *argv[1:]]

        exec_path = shutil.which(argv0)
        if exec_path:
            return exec_path, [argv0, *argv[1:]]

        # 回退到 python -m <module>
        return sys.executable, [sys.executable, "-m", argv0, *argv[1:]]


# 全局单例
installation_manager = InstallationManager()
