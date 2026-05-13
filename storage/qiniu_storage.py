import os
import re
from typing import Optional, Union
from pathlib import Path

from dotenv import load_dotenv
import yaml

load_dotenv()


class StorageConfig:
    def __init__(self, config_path: Optional[Path] = None):
        config_path = config_path or Path(__file__).resolve().parents[1] / "config" / "storage.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
        self.config = self._resolve_env_vars(raw_config)

    def _resolve_env_vars(self, config: dict) -> dict:
        def resolve(value):
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                return os.getenv(env_var, value)
            elif isinstance(value, dict):
                return {k: resolve(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [resolve(item) for item in value]
            return value

        return resolve(config)

    @property
    def bucket_name(self) -> str:
        return self.config["qiniu"]["bucket_name"]

    @property
    def domain(self) -> str:
        domain = self.config["qiniu"]["domain"]
        return domain if domain.startswith("http") else f"https://{domain}"

    @property
    def access_key(self) -> str:
        return self.config["qiniu"]["access_key"]

    @property
    def secret_key(self) -> str:
        return self.config["qiniu"]["secret_key"]

    def path_prefix(self, module: str) -> str:
        return self.config["path_prefixes"].get(module, module)

    def expiration_days(self, module: str) -> Optional[int]:
        return self.config["expiration"].get(f"{module}_days")

    def expiration_hours(self, module: str) -> Optional[int]:
        return self.config["expiration"].get(f"{module}_hours")


class QiniuStorage:
    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()
        self._auth = None

    @property
    def auth(self):
        if self._auth is None:
            from qiniu import Auth
            self._auth = Auth(self.config.access_key, self.config.secret_key)
        return self._auth

    def _safe_user_segment(self, user_id: str) -> str:
        return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in user_id).strip("._") or "anonymous"

    def _normalize_filename(self, filename: str) -> str:
        return re.sub(r"[^\w\-_.]", "_", Path(filename).name)

    def build_key(self, module: str, user_id: str, filename: str) -> str:
        prefix = self.config.path_prefix(module)
        safe_user_id = self._safe_user_segment(user_id)
        safe_filename = self._normalize_filename(filename)
        return f"{prefix}/{safe_user_id}/{safe_filename}"

    def _calculate_expires(self, module: str) -> Optional[int]:
        """Calculate expires time in seconds based on module configuration."""
        # Check for hours first (office)
        hours = self.config.expiration_hours(module)
        if hours is not None:
            return hours * 3600  # Convert hours to seconds

        # Check for days (data)
        days = self.config.expiration_days(module)
        if days is not None:
            return days * 86400  # Convert days to seconds

        # No expiration (knowledge)
        return None

    def build_key_with_id(self, module: str, user_id: str, file_id: str, filename: str) -> str:
        prefix = self.config.path_prefix(module)
        safe_user_id = self._safe_user_segment(user_id)
        safe_filename = self._normalize_filename(filename)
        ext = Path(safe_filename).suffix
        return f"{prefix}/{safe_user_id}/{file_id}{ext}"

    def get_upload_token(self, key: str, expires: Optional[int] = None) -> str:
        return self.auth.upload_token(self.config.bucket_name, key=key, expires=expires)

    def upload_file(self, module: str, user_id: str, file_path: Union[str, Path], filename: Optional[str] = None) -> str:
        from qiniu import put_file

        file_path = Path(file_path)
        filename = filename or file_path.name
        key = self.build_key(module, user_id, filename)

        # Calculate expires based on module
        expires = self._calculate_expires(module)

        token = self.get_upload_token(key, expires)
        ret, info = put_file(up_token=token, key=key, file_path=str(file_path))

        if info.status_code == 200:
            return f"{self.config.domain}/{key}"
        raise Exception(f"七牛云上传失败: {info.error}")

    def upload_content(self, module: str, user_id: str, content: bytes, filename: str) -> str:
        from qiniu import put_data

        key = self.build_key(module, user_id, filename)

        # Calculate expires based on module
        expires = self._calculate_expires(module)

        token = self.get_upload_token(key, expires)
        ret, info = put_data(up_token=token, key=key, data=content)

        if info.status_code == 200:
            return f"{self.config.domain}/{key}"
        raise Exception(f"七牛云上传失败: {info.error}")

    def delete_file(self, url_or_key: str) -> bool:
        from qiniu import BucketManager

        key = url_or_key.replace(self.config.domain + "/", "").replace(self.config.domain, "")
        if not key.startswith(("data/", "knowledge/", "office/")):
            key = None

        if not key:
            return False

        bucket = BucketManager(self.auth)
        ret, info = bucket.delete(self.config.bucket_name, key)
        return info.status_code == 200

    def get_download_url(self, url: str, expires: int = 3600) -> str:
        if url.startswith(self.config.domain):
            key = url.replace(self.config.domain + "/", "")
            return self.auth.private_download_url(url, expires=expires)
        return url


_global_storage: Optional[QiniuStorage] = None


def get_qiniu_storage() -> QiniuStorage:
    global _global_storage
    if _global_storage is None:
        _global_storage = QiniuStorage()
    return _global_storage
