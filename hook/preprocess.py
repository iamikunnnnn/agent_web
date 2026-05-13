import os
import sqlite3
import uuid
from pathlib import Path

from agno.run.agent import RunInput
from agno.utils.log import logger
from storage import get_qiniu_storage

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
    """
    储存文件元数据
    Args:
        user_id:
        data_path:

    Returns:

    """
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


def preprocess_hook(run_input: RunInput) -> dict:
    """
    文件上传预处理钩子：本地保存 + 七牛云上传 + 数据库记录 + 结果拼接
    Args:
        run_input: 运行时输入对象，包含 files 文件列表、input_content 文本内容
    Returns:
        空字典（无额外返回值）
    """
    # 1. 解析用户ID + 创建用户专属临时目录
    user_id = _resolve_user_id(run_input)
    target_dir = _resolve_target_dir(user_id)
    target_dir = Path(target_dir)  # 统一转为 Path 对象，更安全
    target_dir.mkdir(parents=True, exist_ok=True)  # 递归创建，已存在不报错

    # 存储所有文件的 本地路径 / 云端URL
    file_paths: list[str] = []
    file_urls: list[str] = []

    # 2. 处理上传的文件列表
    if run_input.files:
        storage = get_qiniu_storage()  # 获取七牛云存储实例

        for file in run_input.files:
            # ---------------------- 文件名处理 ----------------------
            # 优先取 file.name / file.filename，都没有则生成随机名
            file_name = (
                getattr(file, "name", None)
                or getattr(file, "filename", None)
                or f"upload_{uuid.uuid4().hex[:8]}"
            )

            # ---------------------- 保存到本地临时目录 ----------------------
            dest_path = target_dir / file_name
            try:
                with open(dest_path, "wb") as f:
                    f.write(file.content)
                logger.info(f"文件本地保存成功 | user_id={user_id} | path={dest_path}")
            except Exception as e:
                logger.error(f"文件本地保存失败 | user_id={user_id} | file={file_name} | err={str(e)}")
                continue  # 本地保存失败，跳过该文件

            # ---------------------- 上传到七牛云（长期存储） ----------------------
            try:
                file_url = storage.upload_file(
                    module="data",
                    user_id=user_id,
                    file_path=dest_path,
                    filename=file_name
                )
                logger.info(f"七牛云上传成功 | user_id={user_id} | url={file_url}")
                file_urls.append(file_url)

                # 上传成功后，清理本地临时文件
                try:
                    dest_path.unlink(missing_ok=True)
                    logger.info(f"已删除本地临时文件: {dest_path}")
                except Exception as e:
                    logger.warning(f"删除本地临时文件失败: {dest_path}, {e}")

            except Exception as exc:
                logger.error(f"七牛云上传失败 | err={str(exc)}")
                # 上传失败，直接赋值错误信息到 input_content，不使用本地文件
                error_msg = f"🚫 {file_name} 文件上传七牛云失败，功能维护中，暂不可使用。\n   错误信息：{str(exc)}"
                if run_input.input_content:
                    run_input.input_content = f"{error_msg}\n\n{run_input.input_content}"
                else:
                    run_input.input_content = error_msg
                # 跳过后续处理
                continue

            # 把本地路径赋值给 file 对象，供后续流程使用
            file.filepath = str(dest_path)

            # ---------------------- 保存文件映射到数据库（仅上传成功时） ----------------------
            # 如果 file_urls 有值（即上传成功），才记录到数据库
            if file_urls:
                try:
                    _save_to_db(user_id, file_urls[-1])
                except RuntimeError as exc:
                    logger.error(f"数据库写入失败，已跳过 | err={str(exc)}")

            # 记录本地路径
            file_paths.append(str(dest_path))

    # 3. 清理可能残留的空目录
    if target_dir.exists():
        try:
            # 删除空的用户临时目录
            for parent in [target_dir] + list(target_dir.parents):
                if parent == WORKSPACE_ROOT:
                    break  # 不删除 WORKSPACE_ROOT 本身
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                    logger.info(f"已清理空目录: {parent}")
        except Exception as e:
            logger.warning(f"清理目录失败: {e}")

    # 4. 打印本次处理总文件数
    logger.info(f"文件处理完成 | 总数={len(file_paths)} | user_id={user_id}")

    # 5. 把文件处理结果拼接到输入内容中，供下游使用
    if file_urls:
        result_lines = [f"✅ 成功接收 {len(file_urls)} 个文件：\n"]

        for path, url in zip(file_paths, file_urls):
            # 计算文件大小（MB）
            file_size = os.path.getsize(path)
            size_mb = round(file_size / (1024 * 1024), 2)

            # 拼接文件详情
            result_lines.append(
                f"📄 {os.path.basename(path)}\n"
                f"   云存储URL: {url}\n"
                f"   文件大小: {size_mb} MB\n"
                "----------------------------------------\n"
            )

        result = "".join(result_lines)
        logger.info("\n" + result)  # 格式化输出日志

        # 把结果拼接到原始输入内容前面
        original_input = run_input.input_content or ""
        run_input.input_content = f"{result}\n{original_input}"
    elif file_paths:
        # 有本地文件但没有云URL（上传全部失败）
        if run_input.input_content:
            run_input.input_content = f"{run_input.input_content}"
        # 错误信息已经在循环中赋值了
    else:
        logger.warning("⚠️ 当前请求未接收到任何有效文件")

    return {}
