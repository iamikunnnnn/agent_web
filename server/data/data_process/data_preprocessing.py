"""
前提条件，用户已经存储了数据，在数据库中由user_id对data_path的对应

数据预处理工具（函数式版本，带进程内 per-user 锁）

设计目标：
- 不使用类实例，每个函数都是一个“完整任务”：
    1) 根据 DB 元数据（user_id）查到数据文件路径
    2) 从 CSV 读取为 DataFrame
    3) 使用 pandas / numpy / sklearn 做预处理
    4) 将结果写回同一个 CSV 文件
- 对同一个 user_id，读→处理→写回 这一整段逻辑使用线程锁，避免并发写冲突
- 方便封装为 MCP 工具，由 agent 决定具体参数。


"""

import os
import sqlite3
import threading
from functools import wraps
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.impute import KNNImputer
from sklearn.preprocessing import LabelEncoder, MinMaxScaler, StandardScaler

load_dotenv()
# === per-user 进程内锁 ===

_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_GLOBAL = threading.Lock()


def _get_user_lock(user_id: Union[int, str]="test_user") -> threading.Lock:
    """
    为每个 user_id 维护一个进程内互斥锁，用于保护该用户数据的读写。
    """
    key = str(user_id)
    with _LOCKS_GLOBAL:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


def with_user_lock(func):
    """
    装饰器：保证同一个 user_id 的任务在本进程内串行执行。
    """

    @wraps(func)
    def wrapper(user_id: Union[int, str], *args, **kwargs):
        lock = _get_user_lock(user_id)
        with lock:
            return func(user_id, *args, **kwargs)

    return wrapper


# === 数据源 / 元数据工具 ===


def _get_db_path() -> str:
    """
    获取元数据库路径（存放 user_id -> data_path 映射）。

    优先从环境变量 DATA_DB_PATH 读取。
    """
    db_path = os.getenv("DATA_DB_PATH")
    if not db_path:
        raise RuntimeError("环境变量 DATA_DB_PATH 未设置，无法定位元数据库")
    return db_path


def _get_data_path_by_user(user_id: Union[int, str]="test_user") -> str:
    """
    从 SQLite 元数据库中查询指定 user_id 对应的数据文件路径。
    """
    db_path = _get_db_path()
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data_path FROM user_data WHERE user_id = ? "
                "ORDER BY rowid DESC LIMIT 1;",
                (str(user_id),),
            )
            row = cursor.fetchone()
    except sqlite3.Error as exc:
        raise RuntimeError(f"查询元数据库失败: {exc}") from exc

    if row is None or not row[0]:
        raise ValueError(f"未找到 user_id={user_id} 对应的数据路径")

    data_path = row[0]
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"元数据库中的 data_path 不存在: {data_path}")
    return data_path


def _load_user_dataframe(user_id: Union[int, str]="test_user") -> Tuple[pd.DataFrame, str]:
    """
    按 user_id 加载用户数据为 DataFrame，并返回 (df, data_path)。
    """
    data_path = _get_data_path_by_user(user_id)
    try:
        df = pd.read_csv(data_path)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"读取数据文件失败: {data_path}") from exc
    return df, data_path


def _save_user_dataframe(data_path: str, df: pd.DataFrame) -> None:
    """
    将 DataFrame 写回指定 CSV 路径（覆盖写）。

    采用临时文件 + os.replace，保证写入过程不出现“半写入”的中间状态。
    """
    tmp_path = data_path + ".tmp"
    df.to_csv(tmp_path, index=False)
    os.replace(tmp_path, data_path)


def _normalize_columns_arg(
    df: pd.DataFrame,
    columns: Optional[Union[str, Sequence[str]]],
) -> List[str]:
    """
    将 columns 参数规范化为存在于 df 中的列名列表。
    """
    if columns is None:
        return list(df.columns)
    if isinstance(columns, str):
        columns = [columns]
    normalized: List[str] = []
    for col in columns:
        if col in df.columns:
            normalized.append(col)
    if not normalized:
        raise ValueError("指定的列在数据中均不存在")
    return normalized


# === 缺失值处理 ===


@with_user_lock
def fill_null_with_value(
    user_id: Union[int, str],
    columns: Optional[Union[str, Sequence[str]]] = None,
    value: Union[int, float, str] = 0,
) -> pd.DataFrame:
    """
    将指定列中的缺失值填充为给定常数，并写回文件。
    """
    df, path = _load_user_dataframe(user_id)
    target_cols = _normalize_columns_arg(df, columns)
    df[target_cols] = df[target_cols].fillna(value)
    _save_user_dataframe(path, df)
    return df


@with_user_lock
def fill_null_with_mean(
    user_id: Union[int, str],
    columns: Optional[Union[str, Sequence[str]]] = None,
) -> pd.DataFrame:
    """
    使用均值填充数值列中的缺失值。
    """
    df, path = _load_user_dataframe(user_id)
    target_cols = _normalize_columns_arg(df, columns)
    numeric_cols = [
        col
        for col in target_cols
        if pd.api.types.is_numeric_dtype(df[col])
    ]
    if not numeric_cols:
        return df
    means = df[numeric_cols].mean()
    df[numeric_cols] = df[numeric_cols].fillna(means)
    _save_user_dataframe(path, df)
    return df


@with_user_lock
def fill_null_with_median(
    user_id: Union[int, str],
    columns: Optional[Union[str, Sequence[str]]] = None,
) -> pd.DataFrame:
    """
    使用中位数填充数值列中的缺失值。
    """
    df, path = _load_user_dataframe(user_id)
    target_cols = _normalize_columns_arg(df, columns)
    numeric_cols = [
        col
        for col in target_cols
        if pd.api.types.is_numeric_dtype(df[col])
    ]
    if not numeric_cols:
        return df
    medians = df[numeric_cols].median()
    df[numeric_cols] = df[numeric_cols].fillna(medians)
    _save_user_dataframe(path, df)
    return df


@with_user_lock
def fill_null_with_knn(
    user_id: Union[int, str],
    columns: Optional[Union[str, Sequence[str]]] = None,
    n_neighbors: int = 5,
) -> pd.DataFrame:
    """
    使用 KNNImputer 填充数值列中的缺失值。
    """
    df, path = _load_user_dataframe(user_id)

    if columns is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    else:
        target_cols = _normalize_columns_arg(df, columns)
        numeric_cols = [
            col
            for col in target_cols
            if pd.api.types.is_numeric_dtype(df[col])
        ]

    if not numeric_cols:
        return df

    imputer = KNNImputer(n_neighbors=n_neighbors)
    df[numeric_cols] = imputer.fit_transform(df[numeric_cols])
    _save_user_dataframe(path, df)
    return df


# === 行 / 列筛选 ===


@with_user_lock
def drop_null_rows(
    user_id: Union[int, str],
    columns: Optional[Union[str, Sequence[str]]] = None,
) -> pd.DataFrame:
    """
    删除包含缺失值的行。

    - 指定 columns 时，只要这些列中有缺失值的行会被删除；
    - 不指定 columns 时，任何列存在缺失的行都会被删除。
    """
    df, path = _load_user_dataframe(user_id)
    if columns is None:
        df = df.dropna()
    else:
        target_cols = _normalize_columns_arg(df, columns)
        df = df.dropna(subset=target_cols)
    df = df.reset_index(drop=True)
    _save_user_dataframe(path, df)
    return df


@with_user_lock
def drop_null_columns(
    user_id: Union[int, str],
    columns: Union[str, Sequence[str]],
) -> pd.DataFrame:
    """
    删除指定列。
    """
    df, path = _load_user_dataframe(user_id)
    target_cols = _normalize_columns_arg(df, columns)
    df = df.drop(columns=target_cols)
    _save_user_dataframe(path, df)
    return df


@with_user_lock
def sample_rows(
    user_id: Union[int, str],
    n: Optional[int] = None,
    frac: Optional[float] = None,
    random_state: Optional[int] = None,
) -> pd.DataFrame:
    """
    从数据中进行行级采样。
    """
    df, path = _load_user_dataframe(user_id)
    df = df.sample(n=n, frac=frac, random_state=random_state).reset_index(drop=True)
    _save_user_dataframe(path, df)
    return df


# === 编码与哑变量 ===


@with_user_lock
def get_dummy_data(
    user_id: Union[int, str],
    columns: Union[str, Sequence[str]],
    prefix_sep: str = "_",
) -> pd.DataFrame:
    """
    对指定类别列做 one-hot 编码，并写回。
    """
    df, path = _load_user_dataframe(user_id)
    target_cols = _normalize_columns_arg(df, columns)

    dummies = pd.get_dummies(df[target_cols], prefix=target_cols, prefix_sep=prefix_sep)
    df = pd.concat([df.drop(columns=target_cols), dummies], axis=1)
    _save_user_dataframe(path, df)
    return df


@with_user_lock
def label_encoding(
    user_id: Union[int, str],
    columns: Union[str, Sequence[str]],
) -> pd.DataFrame:
    """
    对指定列做标签编码（LabelEncoder），非数值/类别列会被跳过。
    """
    df, path = _load_user_dataframe(user_id)
    target_cols = _normalize_columns_arg(df, columns)

    for col in target_cols:
        if df[col].isna().all():
            continue
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col].astype(str))

    _save_user_dataframe(path, df)
    return df


# === 数值缩放与规范化 ===


@with_user_lock
def standard_scaling(
    user_id: Union[int, str],
    columns: Optional[Union[str, Sequence[str]]] = None,
) -> pd.DataFrame:
    """
    使用 StandardScaler 对数值列进行标准化（均值 0，方差 1）。
    """
    df, path = _load_user_dataframe(user_id)
    if columns is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    else:
        target_cols = _normalize_columns_arg(df, columns)
        numeric_cols = [
            col
            for col in target_cols
            if pd.api.types.is_numeric_dtype(df[col])
        ]

    if not numeric_cols:
        return df

    scaler = StandardScaler()
    df[numeric_cols] = scaler.fit_transform(df[numeric_cols])
    _save_user_dataframe(path, df)
    return df


@with_user_lock
def normalize_minmax(
    user_id: Union[int, str],
    columns: Optional[Union[str, Sequence[str]]] = None,
    feature_range: Tuple[float, float] = (0.0, 1.0),
) -> pd.DataFrame:
    """
    使用 MinMaxScaler 将数值列缩放到给定范围。
    """
    df, path = _load_user_dataframe(user_id)
    if columns is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    else:
        target_cols = _normalize_columns_arg(df, columns)
        numeric_cols = [
            col
            for col in target_cols
            if pd.api.types.is_numeric_dtype(df[col])
        ]

    if not numeric_cols:
        return df

    scaler = MinMaxScaler(feature_range=feature_range)
    df[numeric_cols] = scaler.fit_transform(df[numeric_cols])
    _save_user_dataframe(path, df)
    return df


# === 异常值处理 ===


@with_user_lock
def remove_outliers_iqr(
    user_id: Union[int, str],
    columns: Optional[Union[str, Sequence[str]]] = None,
    threshold: float = 1.5,
) -> pd.DataFrame:
    """
    使用 IQR（四分位距）过滤异常值（删除超出范围的行）。
    """
    df, path = _load_user_dataframe(user_id)
    if columns is None:
        target_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    else:
        target_cols = _normalize_columns_arg(df, columns)

    for col in target_cols:
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lower = q1 - threshold * iqr
        upper = q3 + threshold * iqr
        df = df[(df[col] >= lower) & (df[col] <= upper)]

    df = df.reset_index(drop=True)
    _save_user_dataframe(path, df)
    return df


@with_user_lock
def cap_outliers_iqr(
    user_id: Union[int, str],
    columns: Optional[Union[str, Sequence[str]]] = None,
    threshold: float = 1.5,
) -> pd.DataFrame:
    """
    使用 IQR 将异常值截断到范围边界（不删除行，只截断数值）。
    """
    df, path = _load_user_dataframe(user_id)
    if columns is None:
        target_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    else:
        target_cols = _normalize_columns_arg(df, columns)

    for col in target_cols:
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lower = q1 - threshold * iqr
        upper = q3 + threshold * iqr
        df[col] = df[col].clip(lower=lower, upper=upper)

    _save_user_dataframe(path, df)
    return df


# === 其他变换 ===


@with_user_lock
def log_transform(
    user_id: Union[int, str],
    columns: Union[str, Sequence[str]],
    add_constant: float = 1.0,
) -> pd.DataFrame:
    """
    对指定列进行对数变换，生成新列 `<col>_log`。
    """
    df, path = _load_user_dataframe(user_id)
    target_cols = _normalize_columns_arg(df, columns)

    for col in target_cols:
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        df[f"{col}_log"] = np.log(df[col] + add_constant)

    _save_user_dataframe(path, df)
    return df


@with_user_lock
def merge_rare_categories(
    user_id: Union[int, str],
    columns: Union[str, Sequence[str]],
    threshold: float = 0.05,
    new_category: str = "Other",
) -> pd.DataFrame:
    """
    合并类别列中的低频类别。
    """
    df, path = _load_user_dataframe(user_id)
    target_cols = _normalize_columns_arg(df, columns)

    for col in target_cols:
        if df[col].isna().all():
            continue
        freq = df[col].value_counts(normalize=True)
        rare = freq[freq < threshold].index
        df[col] = df[col].replace(rare, new_category)

    _save_user_dataframe(path, df)
    return df


__all__ = [
    # 缺失值处理
    "fill_null_with_value",
    "fill_null_with_mean",
    "fill_null_with_median",
    "fill_null_with_knn",
    # 行 / 列操作
    "drop_null_rows",
    "drop_null_columns",
    "sample_rows",
    # 编码
    "get_dummy_data",
    "label_encoding",
    # 数值缩放
    "standard_scaling",
    "normalize_minmax",
    # 异常值
    "remove_outliers_iqr",
    "cap_outliers_iqr",
    # 其他
    "log_transform",
    "merge_rare_categories",
]

