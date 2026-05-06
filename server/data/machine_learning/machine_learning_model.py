"""
前提条件，用户已经存储了数据，在数据库中由user_id对data_path的对应

机器学习模型训练工具（函数式 + 多进程）

设计目标：
- 不再使用类实例，每次训练调用一个纯函数：
    1) 根据 user_id 从数据 DB 元数据中找到 CSV 路径
    2) 读取数据，按照给定 X 列 / y 列和 mode（回归/分类）划分训练集和测试集
    3) 构建 scikit-learn 模型，支持自定义超参数和可选 BayesSearchCV 调参
    4) 训练、评估并保存模型到 .joblib 文件
- 提供基于 ProcessPoolExecutor 的多进程训练提交接口，适合分钟级长时间训练。
"""

import inspect
import os
from datetime import datetime
from typing import Any, Dict, Optional, Sequence, Tuple, Union

import joblib
import pandas as pd
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.svm import SVC, SVR
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from server.data.data_process.data_preprocessing import _load_user_dataframe
from server.data.machine_learning.param import get_model_param_spaces

# === 模型映射（与旧版保持一致的 key） ===

# 注意：这里的 key 与 param.py 中定义的 model_name 保持一致
REGRESSION_MODE = "回归"
CLASSIFICATION_MODE = "分类"

REGRESSION_MODE_ALIASES = {REGRESSION_MODE, "regression"}
CLASSIFICATION_MODE_ALIASES = {CLASSIFICATION_MODE, "classification"}


MODEL_DICT_REGRESSION: Dict[str, Any] = {
    "KNN": KNeighborsRegressor,
    "线性回归": LinearRegression,
    "决策树回归": DecisionTreeRegressor,
    "随机森林回归": RandomForestRegressor,
    "梯度提升回归": GradientBoostingRegressor,
    "支持向量机回归": SVR,
}

MODEL_DICT_CLASSIFICATION: Dict[str, Any] = {
    "KNN": KNeighborsClassifier,
    "逻辑回归": LogisticRegression,
    "决策树分类": DecisionTreeClassifier,
    "随机森林分类": RandomForestClassifier,
    "梯度提升分类": GradientBoostingClassifier,
    "支持向量机分类": SVC,
}


def _resolve_mode(mode: str) -> str:
    """将 mode 标准化为 '回归' 或 '分类'."""
    if mode in REGRESSION_MODE_ALIASES:
        return REGRESSION_MODE
    if mode in CLASSIFICATION_MODE_ALIASES:
        return CLASSIFICATION_MODE
    raise ValueError(f"未知的 mode：{mode}，期望 '回归' 或 '分类'")


def _get_model_dict(mode: str) -> Dict[str, Any]:
    mode_norm = _resolve_mode(mode)
    return MODEL_DICT_REGRESSION if mode_norm == REGRESSION_MODE else MODEL_DICT_CLASSIFICATION


def _build_model(
    model_name: str,
    mode: str,
    model_param: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    根据 model_name + mode 构建 sklearn 模型实例，并过滤掉无效参数。
    """
    model_dict = _get_model_dict(mode)
    if model_name not in model_dict:
        raise ValueError(f"模型名称 {model_name} 不在支持列表中: {list(model_dict.keys())}")

    model_class = model_dict[model_name]

    if model_param is None:
        return model_class()

    valid_keys = inspect.signature(model_class).parameters.keys()
    filtered_params = {k: v for k, v in model_param.items() if k in valid_keys}
    return model_class(**filtered_params)


def _train_test_split(
    df: pd.DataFrame,
    X_columns: Sequence[str],
    y_column: Union[str, Sequence[str]],
    mode: str,
    test_size: float = 0.2,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """
    按照旧版逻辑封装的划分函数：
    - 回归：普通 train_test_split
    - 分类：过滤掉样本数为 1 的类别，并使用 stratify 划分
    """
    mode_norm = _resolve_mode(mode)

    if df.isna().sum().sum() > 0:
        raise ValueError("数据中包含缺失值，请先完成缺失值处理后再训练")

    X = df[list(X_columns)].copy()
    y = df[y_column].copy()

    if isinstance(y, pd.DataFrame):
        # 暂只支持单目标
        if isinstance(y_column, Sequence) and len(y_column) == 1:
            y = y.iloc[:, 0]
        else:
            raise ValueError("当前实现暂不支持多目标 y")

    if mode_norm == CLASSIFICATION_MODE:
        counts = y.value_counts()
        valid_classes = counts[counts > 1].index

        mask = y.isin(valid_classes)
        X_filtered = X[mask].copy()
        y_filtered = y[mask].copy()

        X_filtered = X_filtered.reset_index(drop=True)
        y_filtered = y_filtered.reset_index(drop=True)

        if len(X_filtered) == 0:
            raise ValueError("过滤后没有足够样本用于分类训练")

        x_train, x_test, y_train, y_test = train_test_split(
            X_filtered,
            y_filtered,
            test_size=test_size,
            random_state=random_state,
            stratify=y_filtered,
        )
    else:
        X_filtered = X.reset_index(drop=True)
        y_filtered = y.reset_index(drop=True)

        x_train, x_test, y_train, y_test = train_test_split(
            X_filtered,
            y_filtered,
            test_size=test_size,
            random_state=random_state,
        )

    return x_train, x_test, y_train, y_test


def _maybe_bayes_search(
    model: Any,
    model_name: str,
    mode: str,
    x_train: pd.DataFrame,
    y_train: pd.Series,
    n_iter: int = 5,
) -> Tuple[Any, Optional[Dict[str, Any]]]:
    """
    如果 skopt 可用且存在对应的搜索空间，则使用 BayesSearchCV 进行超参数搜索。
    """
    try:
        from sklearn.model_selection import StratifiedKFold
        from skopt import BayesSearchCV  # type: ignore[import]
    except ImportError:
        # 未安装 skopt，直接返回原模型
        return model, None

    try:
        param_spaces_all = get_model_param_spaces()
    except Exception:  # noqa: BLE001
        # 获取搜索空间失败，直接返回原模型
        return model, None

    # 不依赖 mode 作为 key，遍历所有空间寻找匹配的 model_name
    search_space = None
    for _, spaces in param_spaces_all.items():
        if model_name in spaces:
            search_space = spaces[model_name]
            break

    if search_space is None:
        return model, None

    mode_norm = _resolve_mode(mode)
    if mode_norm == CLASSIFICATION_MODE:
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    else:
        # 回归场景简单使用 KFold 等价实现（StratifiedKFold 对回归无意义）
        from sklearn.model_selection import KFold

        cv = KFold(n_splits=5, shuffle=True, random_state=42)

    bayes_search = BayesSearchCV(
        estimator=model,
        search_spaces=search_space,
        cv=cv,
        n_iter=n_iter,
        random_state=42,
    )
    bayes_search.fit(x_train, y_train)
    return bayes_search.best_estimator_, dict(bayes_search.best_params_)


def train_model_once(
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
) -> Dict[str, Any]:
    """
    单次训练任务：
    - 按 user_id 加载数据
    - 构建模型 + 可选 BayesSearch 调参
    - 训练并评估
    - 可选保存模型

    返回：包含指标、最佳参数和模型保存路径的字典。
    """
    mode_norm = _resolve_mode(mode)

    df, _ = _load_user_dataframe(user_id)
    model = _build_model(model_name=model_name, mode=mode_norm, model_param=model_param)
    x_train, x_test, y_train, y_test = _train_test_split(
        df=df,
        X_columns=X_columns,
        y_column=y_column,
        mode=mode_norm,
        test_size=test_size,
        random_state=random_state,
    )

    best_params: Optional[Dict[str, Any]] = None
    if use_bayes_search:
        model, best_params = _maybe_bayes_search(
            model=model,
            model_name=model_name,
            mode=mode_norm,
            x_train=x_train,
            y_train=y_train,
            n_iter=bayes_iter,
        )

    model.fit(x_train, y_train)
    y_pred = model.predict(x_test)

    if mode_norm == REGRESSION_MODE:
        mse = float(mean_squared_error(y_test, y_pred))
        r2 = float(r2_score(y_test, y_pred))
        metrics: Dict[str, Any] = {"mse": mse, "r2": r2}
    else:
        acc = float(accuracy_score(y_test, y_pred))
        labels = sorted(pd.Series(y_test).unique())
        report = classification_report(
            y_test,
            y_pred,
            labels=labels,
            target_names=[str(l) for l in labels],
        )
        metrics = {"accuracy": acc, "classification_report": report}

    model_path: Optional[str] = None
    if save_model:
        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{model_name}_{timestamp}.joblib"
        model_path = os.path.join(save_dir, filename)
        joblib.dump(model, model_path)

    return {
        "user_id": str(user_id),
        "mode": mode_norm,
        "model_name": model_name,
        "model_param": model_param or {},
        "best_params": best_params,
        "metrics": metrics,
        "model_path": model_path,
        "n_train": int(len(x_train)),
        "n_test": int(len(x_test)),
    }

