import os
import sqlite3
import uuid
from pathlib import Path

from agno.run.agent import RunInput
from agno.utils.log import logger

WORKSPACE_ROOT = Path(os.getenv("DATA_UPLOAD_DIR", Path(__file__).resolve().parents[1] / "user_cache" / "workspace"))


def _safe_user_segment(user_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in user_id).strip("._") or "anonymous"


def _resolve_user_id(run_input: RunInput) -> str:
    metadata = getattr(run_input, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("user_id", "sub"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    direct_user_id = getattr(run_input, "user_id", None)
    if isinstance(direct_user_id, str) and direct_user_id.strip():
        return direct_user_id.strip()

    fallback_user_id = os.getenv("DEFAULT_DATA_USER_ID", "anonymous")
    logger.warning(f"未从请求上下文解析到 user_id，回退到默认标识: {fallback_user_id}")
    return fallback_user_id


def _resolve_target_dir(user_id: str) -> Path:
    return WORKSPACE_ROOT / _safe_user_segment(user_id)


def _save_to_db(user_id: str, data_path: str) -> None:
    db_path = os.getenv("DATA_DB_PATH")
    if not db_path:
        raise RuntimeError("环境变量 DATA_DB_PATH 未设置，无法写入元数据库")

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_data (
                    user_id   TEXT NOT NULL,
                    data_path TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO user_data (user_id, data_path) VALUES (?, ?)",
                (user_id, data_path),
            )
            conn.commit()
            logger.info(f"已写入数据映射: user_id={user_id}, data_path={data_path}")
    except sqlite3.Error as exc:
        raise RuntimeError(f"写入元数据库失败: {exc}") from exc


def preprocess_hook(run_input: RunInput):
    user_id = _resolve_user_id(run_input)
    target_dir = _resolve_target_dir(user_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    file_paths: list[str] = []

    if run_input.files:
        for file in run_input.files:
            file_name = (
                getattr(file, "name", None)
                or getattr(file, "filename", None)
                or f"upload_{uuid.uuid4().hex[:8]}"
            )

            dest_path = target_dir / file_name

            with open(dest_path, "wb") as f:
                f.write(file.content)
            logger.info(f"文件已保存: user_id={user_id}, path={dest_path}")

            file.filepath = str(dest_path)

            try:
                _save_to_db(user_id, str(dest_path))
            except RuntimeError as exc:
                logger.error(f"写入数据映射失败，已跳过: {exc}")

            file_paths.append(str(dest_path))

    logger.info(f"本次共处理 {len(file_paths)} 个文件，user_id={user_id}")

    if file_paths:
        result_lines = [f"成功接收 {len(file_paths)} 个文件：\n"]
        for path in file_paths:
            size_mb = os.path.getsize(path) / (1024 * 1024)
            result_lines.append(
                f"{os.path.basename(path)}\n"
                f"   路径: {path}\n"
                f"   大小: {size_mb:.2f} MB\n"
            )

        result = "".join(result_lines)
        logger.info(result)

        original_input = run_input.input_content or ""
        run_input.input_content = f"{result}\n{original_input}"
    else:
        logger.warning("当前请求未接收到有效文件")

    return {}
