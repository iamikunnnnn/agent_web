import mimetypes
from pathlib import Path

from markitdown import MarkItDown

WORKSPACE_ROOT = "./user_cache/workspace"
mimetypes.add_type("text/md", ".md")

markItDown = MarkItDown(enable_plugins=False)


class WorkspaceManager:

    def __init__(self, user_id: str):
        """
        初始化 WorkspaceManager 实例
        :param user_id: 用户ID
        """
        self.user_id = user_id
        self.storage_user_dir = f"users/{user_id}"
        self.workspace_user_dir = f"users/{user_id}"

    def init_workspace(self):
        """
        初始化 Agent workspace
        - 检查数据库中的软链是否存在，不存在的初始化
        """

    def _get_storage_task_path(self, task_id: str) -> str:
        return f"{self.storage_user_dir}/tasks/{task_id}"

    def _get_storage_task_references_path(self, task_id: str) -> str:
        return f"{self.storage_user_dir}/tasks/{task_id}/references"

    def _get_storage_task_reference_path(self, task_id: str, ref_id: str) -> str:
        """
        获取某个任务下某个引用（ref）的存储路径
        目录结构：
        {storage_user_dir}/tasks/{task_id}/references/{ref_id}
        """
        return f"{self.storage_user_dir}/tasks/{task_id}/references/{ref_id}"

    def _get_storage_references_path(self, ref_id: str) -> str:
        return f"{self.storage_user_dir}/references/{ref_id}"

    def _get_workspace_agent_path(self) -> str:
        return self.workspace_user_dir

    def _resolve_workspace_uri(self, workspace_uri: str) -> Path:
        """
        将自定义 workspace:// URI 转换为真实的本地文件路径。
        """
        if workspace_uri.startswith("workspace://"):
            relative_path = workspace_uri.removeprefix("workspace://")
            return WORKSPACE_ROOT / relative_path
        else:
            raise ValueError(f"Unsupported URI scheme in: {workspace_uri}")

    def resolve_abs_file_path(self, workspace_uri: str) -> str:
        path = self._resolve_workspace_uri(workspace_uri)
        if not path.exists():
            print(f"file not exists: {workspace_uri}")
            raise FileNotFoundError(f"File not found: {workspace_uri}")
        return str(path)
