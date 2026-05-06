import os
import sqlite3
import uuid

from agno.run.agent import RunInput
from agno.utils.log import logger

# ===== 目标保存目录 =====
TARGET_DIR = r"C:\Users\WUJIEAI\PycharmProjects\my_agents_newFeatureExplore\agent_manage\user_cache\workspace"


def _save_to_db(user_id: str, data_path: str) -> None:
    db_path = os.getenv("DATA_DB_PATH")
    if not db_path:
        raise RuntimeError("环境变量 DATA_DB_PATH 未设置，无法写入元数据库")

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_data (
                    user_id   TEXT NOT NULL,
                    data_path TEXT NOT NULL
                )
            """)
            cursor.execute(
                "INSERT INTO user_data (user_id, data_path) VALUES (?, ?)",
                (user_id, data_path),
            )
            conn.commit()
            logger.info(f"💾 数据库记录已写入: user_id={user_id}, data_path={data_path}")
    except sqlite3.Error as exc:
        raise RuntimeError(f"写入元数据库失败: {exc}") from exc


def preprocess_hook(
        run_input: RunInput,
):
    user_id = "JinDong"
    os.makedirs(TARGET_DIR, exist_ok=True)

    file_paths = []

    if run_input.files:
        for file in run_input.files:
            # 取文件名
            file_name = (
                getattr(file, "name", None)
                or getattr(file, "filename", None)
                or f"upload_{uuid.uuid4().hex[:8]}"
            )

            dest_path = os.path.join(TARGET_DIR, file_name)

            # 将 file 复制到 TARGET_DIR
            with open(dest_path, "wb") as f:
                f.write(file.content)
            logger.info(f"📁 文件已保存到: {dest_path}")

            # 用 TARGET_DIR 下的路径替代原来的 filepath
            file.filepath = dest_path

            # 写入数据库
            try:
                _save_to_db(user_id, dest_path)
            except RuntimeError as e:
                logger.error(f"❌ 数据库写入失败，跳过: {e}")

            file_paths.append(dest_path)

    logger.info(f"共处理 {len(file_paths)} 个文件: {file_paths}")

    if file_paths:
        result_lines = [f"✅ 成功接收 {len(file_paths)} 个文件：\n"]
        for path in file_paths:
            size_mb = os.path.getsize(path) / (1024 * 1024)
            result_lines.append(
                f"📄 {os.path.basename(path)}\n"
                f"   路径: {path}\n"
                f"   大小: {size_mb:.2f} MB\n"
            )

        result = "".join(result_lines)
        logger.info(result)

        original_input = run_input.input_content or ''
        run_input.input_content = f"{result}\n{original_input}"
    else:
        logger.warning("⚠️ 未接收到任何有效文件")

    return {}
