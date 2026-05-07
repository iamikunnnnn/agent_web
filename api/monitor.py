from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import httpx
from agno.utils.log import logger
from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from prometheus_fastapi_instrumentator import Instrumentator

# --------------------------------------------------------------------------- #
# 类型别名
# MetricFetcher    : 接收 db_id，异步返回指标字典的函数
# MetricRefresher  : 接收 db_id，异步触发后端刷新的函数
# SnapshotRefresher: 无参数，异步刷新全量快照的函数
# --------------------------------------------------------------------------- #
MetricFetcher = Callable[[str], Awaitable[dict[str, Any]]]
MetricRefresher = Callable[[str], Awaitable[None]]
SnapshotRefresher = Callable[[], Awaitable[None]]

# --------------------------------------------------------------------------- #
# 通用日维度指标字段映射
# 每个元组格式: (API 响应字段名, _AgnoCollectors 中对应的属性名)
# 同一份映射表同时用于：
#   - 按 db_id 写入 daily_* Gauge（_set_db_gauge_values）
#   - 跨 db 加总写入 all_daily_* Gauge（_recompute_aggregate_collectors）
# --------------------------------------------------------------------------- #
_DAILY_METRIC_FIELDS: tuple[tuple[str, str], ...] = (
    ("agent_runs_count", "daily_agent_runs"),
    ("agent_sessions_count", "daily_agent_sessions"),
    ("team_runs_count", "daily_team_runs"),
    ("team_sessions_count", "daily_team_sessions"),
    ("workflow_runs_count", "daily_workflow_runs"),
    ("workflow_sessions_count", "daily_workflow_sessions"),
    ("users_count", "daily_users"),
)

# --------------------------------------------------------------------------- #
# Token 维度指标字段映射，结构同上。
# token_metrics 是 API 响应中的嵌套字典，因此单独列出。
# --------------------------------------------------------------------------- #
_TOKEN_METRIC_FIELDS: tuple[tuple[str, str], ...] = (
    ("input_tokens", "daily_input_tokens"),
    ("output_tokens", "daily_output_tokens"),
    ("total_tokens", "daily_total_tokens"),
    ("cache_read_tokens", "daily_cache_read_tokens"),
    ("cache_write_tokens", "daily_cache_write_tokens"),
    ("reasoning_tokens", "daily_reasoning_tokens"),
    ("audio_total_tokens", "daily_audio_tokens"),
)


# =========================================================================== #
# 数据模型层
# 定义贯穿整个模块的核心数据结构，不包含任何业务逻辑。
# _ExporterState : 刷新生命周期的运行时状态
# _AgnoCollectors: 所有 Prometheus 指标对象的容器
# =========================================================================== #

@dataclass
class _ExporterState:
    """
    Prometheus Exporter 的运行时状态，贯穿整个刷新生命周期。

    Attributes:
        refresh_interval_s       : 两次自动刷新之间的最小间隔（秒）。
        lookback_days            : 查询指标时向前回溯的天数。
        db_ids                   : 需要采集指标的数据库 ID 列表。
        lock                     : 异步互斥锁，防止并发刷新。
        last_refresh_started_at  : 上次刷新开始的 Unix 时间戳（秒）。
        last_refresh_completed_at: 上次刷新完成的 Unix 时间戳（秒）；0 表示从未刷新。
        last_refresh_duration_s  : 上次刷新耗时（秒）。
        last_refresh_error       : 上次刷新失败时的错误信息；成功则为 None。
    """

    refresh_interval_s: int
    lookback_days: int
    db_ids: list[str]
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_refresh_started_at: float = 0.0
    last_refresh_completed_at: float = 0.0
    last_refresh_duration_s: float = 0.0
    last_refresh_error: str | None = None


@dataclass
class _AgnoCollectors:
    """
    封装所有向 Prometheus 注册的 Gauge / Counter 对象。

    指标分为三层：

    1. **单库指标**（daily_* 系列，带 db_id 标签）
       按数据库维度记录业务指标，适合在 Grafana 中按库筛选或对比。

    2. **全局聚合指标**（all_daily_* 系列，无 db_id 标签）
       对所有 db 的同名指标求和，提供整体视图，无需在查询时手动 sum()。
       模型维度的聚合（all_daily_model_runs）按 model_id + provider 合并，
       同一模型在不同 db 的调用次数会被叠加。

    3. **Exporter 元指标**（exporter_* 系列）
       描述 Exporter 自身健康状态，用于监控采集流程本身的可靠性。

    辅助字段：

        model_series_by_db    : 追踪每个 db 已写入 daily_model_runs 的标签组合，
                                用于下次刷新前清理过时时序，防止"僵尸时序"。
                                （之所以需要单独维护，是因为 daily_model_runs 的标签组合是动态的
                                （模型随时可能上下线），不像 daily_agent_runs 这类指标的标签只有
                                固定的 db_id，覆盖写入就够了，不需要主动删除。）

        aggregate_model_series: 追踪已写入 all_daily_model_runs 的标签组合，
                                同样用于刷新前清理，与单库清理逻辑对称。
    """

    registry: CollectorRegistry

    # ---- 单库日聚合业务指标（按 db_id 标签区分）-----------------------------
    daily_agent_runs: Gauge
    daily_agent_sessions: Gauge
    daily_team_runs: Gauge
    daily_team_sessions: Gauge
    daily_workflow_runs: Gauge
    daily_workflow_sessions: Gauge
    daily_users: Gauge
    daily_input_tokens: Gauge
    daily_output_tokens: Gauge
    daily_total_tokens: Gauge
    daily_cache_read_tokens: Gauge
    daily_cache_write_tokens: Gauge
    daily_reasoning_tokens: Gauge
    daily_audio_tokens: Gauge
    daily_model_runs: Gauge  # 额外按 model_id + provider 细分

    # ---- 全局聚合指标（无 db_id 标签，所有库求和）---------------------------
    all_daily_agent_runs: Gauge
    all_daily_agent_sessions: Gauge
    all_daily_team_runs: Gauge
    all_daily_team_sessions: Gauge
    all_daily_workflow_runs: Gauge
    all_daily_workflow_sessions: Gauge
    all_daily_users: Gauge
    all_daily_input_tokens: Gauge
    all_daily_output_tokens: Gauge
    all_daily_total_tokens: Gauge
    all_daily_cache_read_tokens: Gauge
    all_daily_cache_write_tokens: Gauge
    all_daily_reasoning_tokens: Gauge
    all_daily_audio_tokens: Gauge
    all_daily_model_runs: Gauge  # 按 model_id + provider 合并所有库的调用次数

    # ---- 快照时间戳与 Exporter 元指标 ---------------------------------------
    metrics_updated_at_timestamp_seconds: Gauge
    exporter_refresh_success: Gauge
    exporter_refresh_timestamp_seconds: Gauge
    exporter_refresh_duration_seconds: Gauge
    exporter_refresh_errors_total: Counter
    exporter_db_refresh_success: Gauge
    exporter_db_metrics_freshness_seconds: Gauge

    # ---- 时序追踪辅助字段（用于刷新前清理僵尸时序）-------------------------
    # key: db_id → 该库已写入 daily_model_runs 的 (model_id, provider) 集合
    model_series_by_db: dict[str, set[tuple[str, str]]] = field(default_factory=dict)  # default_factory = 自动创建默认值的工厂
    # 已写入 all_daily_model_runs 的 (model_id, provider) 集合
    aggregate_model_series: set[tuple[str, str]] = field(default_factory=set)


# =========================================================================== #
# 工具函数层
# 纯函数，无副作用，不依赖任何模块级状态。
# 被原子操作层和初始化逻辑调用，本身不属于主调用链的独立一层。
# =========================================================================== #

def _parse_dt(value: Any) -> datetime:
    """
    将各种时间格式统一转换为带 UTC 时区的 datetime 对象。

    支持输入类型：datetime、ISO 8601 字符串（含 'Z' 后缀）、Unix 时间戳（int/float）。
    所有转换失败时静默返回 Unix epoch，确保调用方无需处理 None。

    Args:
        value: 任意时间表示值。

    Returns:
        带 UTC 时区的 datetime，失败时返回 epoch（1970-01-01 00:00:00 UTC）。
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        with suppress(Exception):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        with suppress(Exception):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
    return datetime.fromtimestamp(0, tz=timezone.utc)


def _as_float(value: Any) -> float:
    """
    将任意值安全转换为浮点数，失败时静默返回 0.0。

    适合在批量指标写入中使用，不会因单个字段类型异常而中断整个流程。

    Args:
        value: 待转换的值。

    Returns:
        对应浮点数，失败时返回 0.0。
    """
    with suppress(Exception):
        return float(value)
    return 0.0


def _latest_metric_entry(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    从 API 响应中提取最新一条指标记录。

    Agno 后端的 "metrics" 列表按时间正序排列，从末尾反向遍历取第一个有效字典。

    Args:
        payload: /metrics 接口返回的 JSON 字典。

    Returns:
        最新指标字典；列表为空或格式异常时返回 None。
    """
    metrics = payload.get("metrics") or []
    if not isinstance(metrics, list):
        return None
    return next((metric for metric in reversed(metrics) if isinstance(metric, dict)), None)


def _build_metrics_query_params(*, lookback_days: int) -> dict[str, str]:
    """
    构造查询指标 API 的日期范围参数。

    以今天为结束日期，向前推 lookback_days 天（至少 1 天）作为起始日期。

    Args:
        lookback_days: 回溯天数。

    Returns:
        含 "starting_date" 和 "ending_date" 的字典（ISO 8601 格式）。
    """
    ending = date.today()
    starting = ending - timedelta(days=max(lookback_days, 1))
    return {"starting_date": starting.isoformat(), "ending_date": ending.isoformat()}


def _build_auth_headers(agent_os: Any) -> dict[str, str]:
    """
    从 AgentOS 实例中提取安全密钥，构造 Bearer Token 认证头。

    若密钥不存在则返回空字典，不影响后续流程。

    Args:
        agent_os: AgentOS 实例。

    Returns:
        含或不含 "Authorization" 的请求头字典。
    """
    headers: dict[str, str] = {}
    settings = getattr(agent_os, "settings", None)
    os_key = getattr(settings, "os_security_key", None) if settings else None
    if os_key:
        headers["Authorization"] = f"Bearer {os_key}"
    return headers


# =========================================================================== #
# 初始化层
# 在应用启动时执行一次，负责向 Prometheus 注册所有指标对象。
# 执行后产出 _AgnoCollectors 实例，供整个刷新生命周期复用。
# =========================================================================== #

def _register_agno_collectors(registry: CollectorRegistry) -> _AgnoCollectors:
    """
    向指定 CollectorRegistry 注册所有 Agno 指标，并封装到 _AgnoCollectors 返回。

    注册两套平行的指标：
    - agno_daily_*     : 带 db_id 标签，按库区分。
    - agno_all_daily_* : 无 db_id 标签，跨库聚合总量。

    使用自定义 registry 而非全局注册表，避免命名冲突，也便于测试隔离。

    Args:
        registry: 自定义 CollectorRegistry 实例。

    Returns:
        包含所有已注册指标对象的 _AgnoCollectors 实例。
    """
    return _AgnoCollectors(
        registry=registry,

        # ---- 单库日聚合业务指标（带 db_id 标签）-----------------------------
        daily_agent_runs=Gauge(
            "agno_daily_agent_runs", "Latest daily aggregated agent runs by db.", ["db_id"], registry=registry
        ),
        daily_agent_sessions=Gauge(
            "agno_daily_agent_sessions", "Latest daily aggregated agent sessions by db.", ["db_id"], registry=registry
        ),
        daily_team_runs=Gauge(
            "agno_daily_team_runs", "Latest daily aggregated team runs by db.", ["db_id"], registry=registry
        ),
        daily_team_sessions=Gauge(
            "agno_daily_team_sessions", "Latest daily aggregated team sessions by db.", ["db_id"], registry=registry
        ),
        daily_workflow_runs=Gauge(
            "agno_daily_workflow_runs", "Latest daily aggregated workflow runs by db.", ["db_id"], registry=registry
        ),
        daily_workflow_sessions=Gauge(
            "agno_daily_workflow_sessions",
            "Latest daily aggregated workflow sessions by db.",
            ["db_id"],
            registry=registry,
        ),
        daily_users=Gauge(
            "agno_daily_users", "Latest daily aggregated users by db.", ["db_id"], registry=registry
        ),
        daily_input_tokens=Gauge(
            "agno_daily_input_tokens", "Latest daily aggregated input tokens by db.", ["db_id"], registry=registry
        ),
        daily_output_tokens=Gauge(
            "agno_daily_output_tokens", "Latest daily aggregated output tokens by db.", ["db_id"], registry=registry
        ),
        daily_total_tokens=Gauge(
            "agno_daily_total_tokens", "Latest daily aggregated total tokens by db.", ["db_id"], registry=registry
        ),
        daily_cache_read_tokens=Gauge(
            "agno_daily_cache_read_tokens", "Latest daily aggregated cache read tokens by db.", ["db_id"], registry=registry
        ),
        daily_cache_write_tokens=Gauge(
            "agno_daily_cache_write_tokens",
            "Latest daily aggregated cache write tokens by db.",
            ["db_id"],
            registry=registry,
        ),
        daily_reasoning_tokens=Gauge(
            "agno_daily_reasoning_tokens", "Latest daily aggregated reasoning tokens by db.", ["db_id"], registry=registry
        ),
        daily_audio_tokens=Gauge(
            "agno_daily_audio_tokens", "Latest daily aggregated audio tokens by db.", ["db_id"], registry=registry
        ),
        daily_model_runs=Gauge(
            "agno_daily_model_runs",
            "Latest daily aggregated model runs by db, model, and provider.",
            ["db_id", "model_id", "provider"],
            registry=registry,
        ),

        # ---- 全局聚合指标（无 db_id 标签，对所有库求和）--------------------
        all_daily_agent_runs=Gauge(
            "agno_all_daily_agent_runs", "Latest aggregated agent runs across all dbs.", registry=registry
        ),
        all_daily_agent_sessions=Gauge(
            "agno_all_daily_agent_sessions", "Latest aggregated agent sessions across all dbs.", registry=registry
        ),
        all_daily_team_runs=Gauge(
            "agno_all_daily_team_runs", "Latest aggregated team runs across all dbs.", registry=registry
        ),
        all_daily_team_sessions=Gauge(
            "agno_all_daily_team_sessions", "Latest aggregated team sessions across all dbs.", registry=registry
        ),
        all_daily_workflow_runs=Gauge(
            "agno_all_daily_workflow_runs", "Latest aggregated workflow runs across all dbs.", registry=registry
        ),
        all_daily_workflow_sessions=Gauge(
            "agno_all_daily_workflow_sessions", "Latest aggregated workflow sessions across all dbs.", registry=registry
        ),
        all_daily_users=Gauge(
            "agno_all_daily_users", "Latest aggregated users across all dbs.", registry=registry
        ),
        all_daily_input_tokens=Gauge(
            "agno_all_daily_input_tokens", "Latest aggregated input tokens across all dbs.", registry=registry
        ),
        all_daily_output_tokens=Gauge(
            "agno_all_daily_output_tokens", "Latest aggregated output tokens across all dbs.", registry=registry
        ),
        all_daily_total_tokens=Gauge(
            "agno_all_daily_total_tokens", "Latest aggregated total tokens across all dbs.", registry=registry
        ),
        all_daily_cache_read_tokens=Gauge(
            "agno_all_daily_cache_read_tokens", "Latest aggregated cache read tokens across all dbs.", registry=registry
        ),
        all_daily_cache_write_tokens=Gauge(
            "agno_all_daily_cache_write_tokens", "Latest aggregated cache write tokens across all dbs.", registry=registry
        ),
        all_daily_reasoning_tokens=Gauge(
            "agno_all_daily_reasoning_tokens", "Latest aggregated reasoning tokens across all dbs.", registry=registry
        ),
        all_daily_audio_tokens=Gauge(
            "agno_all_daily_audio_tokens", "Latest aggregated audio tokens across all dbs.", registry=registry
        ),
        all_daily_model_runs=Gauge(
            "agno_all_daily_model_runs",
            "Latest aggregated model runs across all dbs by model and provider.",
            ["model_id", "provider"],   # 无 db_id，跨库合并同一模型的调用量
            registry=registry,
        ),

        # ---- 快照时间戳与 Exporter 元指标 ------------------------------------
        metrics_updated_at_timestamp_seconds=Gauge(
            "agno_metrics_updated_at_timestamp_seconds",
            "Timestamp reported by the latest Agno metrics snapshot.",
            ["db_id"],
            registry=registry,
        ),
        exporter_refresh_success=Gauge(
            "agno_exporter_refresh_success", "Whether the last exporter refresh cycle fully succeeded.", registry=registry
        ),
        exporter_refresh_timestamp_seconds=Gauge(
            "agno_exporter_refresh_timestamp_seconds",
            "Completion timestamp of the latest exporter refresh cycle.",
            registry=registry,
        ),
        exporter_refresh_duration_seconds=Gauge(
            "agno_exporter_refresh_duration_seconds", "Duration of the latest exporter refresh cycle.", registry=registry
        ),
        exporter_refresh_errors_total=Counter(
            "agno_exporter_refresh_errors_total", "Number of exporter refresh failures.", registry=registry
        ),
        exporter_db_refresh_success=Gauge(
            "agno_exporter_db_refresh_success", "Whether the latest refresh succeeded for the db.", ["db_id"], registry=registry
        ),
        exporter_db_metrics_freshness_seconds=Gauge(
            "agno_exporter_db_metrics_freshness_seconds",
            "Age in seconds of the latest Agno metrics snapshot for the db.",
            ["db_id"],
            registry=registry,
        ),
    )


# =========================================================================== #
# 原子操作层
# 每个函数只负责一件具体的事：写单库指标、清理时序、发起单次 HTTP 请求等。
# 被刷新编排层调用，不感知多库循环或聚合逻辑。
# =========================================================================== #

def _set_db_gauge_values(collectors: _AgnoCollectors, *, db_id: str, latest: dict[str, Any] | None) -> None:
    """
    将单个 db 的最新快照数据写入对应的单库 Gauge 指标。（在调用这个函数时会循环，故最终会处理每个db）

    分两步：
    1. 遍历 _DAILY_METRIC_FIELDS，从 latest 顶层字段读取通用业务指标。
    2. 遍历 _TOKEN_METRIC_FIELDS，从 latest["token_metrics"] 嵌套字典读取 token 指标。

    此函数只负责写单库指标（daily_*），全局聚合（all_daily_*）由
    _recompute_aggregate_collectors 在所有库刷新完毕后统一计算。

    Args:
        collectors: 指标容器。
        db_id     : 当前操作的数据库 ID，用于 Gauge 标签。
        latest    : 最新指标快照字典；为 None 时写入 0.0。
    """
    # 将传入的指标填入 collectors，指标在调用这个函数前已经获取
    for field_name, attr_name in _DAILY_METRIC_FIELDS:
        getattr(collectors, attr_name).labels(db_id=db_id).set(_as_float((latest or {}).get(field_name)))

    # 获取 token 指标（嵌套在 latest["token_metrics"] 下）
    token_metrics = (latest or {}).get("token_metrics") or {}
    if not isinstance(token_metrics, dict):
        token_metrics = {}
    # 将传入的 token 指标填入 collectors
    for field_name, attr_name in _TOKEN_METRIC_FIELDS:
        getattr(collectors, attr_name).labels(db_id=db_id).set(_as_float(token_metrics.get(field_name)))


def _clear_model_series(collectors: _AgnoCollectors, *, db_id: str) -> None:
    """
    清除指定 db 在 daily_model_runs 中已注册的所有时序数据。

    Prometheus Gauge 不会自动删除不再写入的标签组合（"僵尸时序"）。
    每次刷新前调用此函数，确保下线的模型不会持续出现在抓取结果中。
    全局聚合（all_daily_model_runs）的清理由 _recompute_aggregate_collectors 负责。

    Args:
        collectors: 指标容器。
        db_id     : 需要清理的数据库 ID。
    """
    for model_id, provider in collectors.model_series_by_db.get(db_id, set()):
        with suppress(KeyError, ValueError):
            collectors.daily_model_runs.remove(db_id, model_id, provider)
    collectors.model_series_by_db[db_id] = set()


def _update_agno_collectors(collectors: _AgnoCollectors, *, db_id: str, payload: dict[str, Any]) -> None:
    """
    将单次 API 响应更新到指定 db 的所有单库 Prometheus 指标。

    执行顺序：
    1. 提取最新快照条目，写入通用业务指标和 token 指标（_set_db_gauge_values）。
    2. 清除旧模型时序，写入最新模型调用次数（daily_model_runs）。
    3. 写入快照时间戳和数据新鲜度。

    注意：此函数不触碰 all_daily_* 聚合指标，聚合由外层的
    _recompute_aggregate_collectors 在所有库更新完毕后集中处理。

    Args:
        collectors: 指标容器。
        db_id     : 当前操作的数据库 ID。
        payload   : /metrics 接口的完整 JSON 响应。
    """
    # 步骤 1：从 payload 中提取最新快照条目，写入通用业务指标及 token 指标
    latest = _latest_metric_entry(payload)
    _set_db_gauge_values(collectors, db_id=db_id, latest=latest)

    # 步骤 2：更新模型维度指标（先清理旧时序，再写入新数据）
    _clear_model_series(collectors, db_id=db_id)
    model_metrics = (latest or {}).get("model_metrics") or []
    if isinstance(model_metrics, list):
        labels_for_db: set[tuple[str, str]] = set()
        for entry in model_metrics:
            if not isinstance(entry, dict):
                continue
            model_id = str(entry.get("model_id") or "")
            provider = str(entry.get("model_provider") or "")
            collectors.daily_model_runs.labels(db_id=db_id, model_id=model_id, provider=provider).set(
                _as_float(entry.get("count"))
            )
            labels_for_db.add((model_id, provider))
        # 记录本次写入的标签组合，供下次刷新时清理
        collectors.model_series_by_db[db_id] = labels_for_db

    # 步骤 3：写入快照时间戳及数据新鲜度
    # 优先使用 payload 顶层的 updated_at，回退到最新 metric 条目的同名字段
    updated_at_raw = payload.get("updated_at") if payload.get("updated_at") is not None else (latest or {}).get("updated_at")
    updated_at = _parse_dt(updated_at_raw)
    updated_at_ts = updated_at.timestamp() if updated_at_raw is not None else 0.0
    collectors.metrics_updated_at_timestamp_seconds.labels(db_id=db_id).set(updated_at_ts)

    # 新鲜度 = 当前时间 - 快照更新时间（秒，最小为 0）
    freshness = max(time.time() - updated_at_ts, 0.0) if updated_at_ts > 0 else 0.0
    collectors.exporter_db_metrics_freshness_seconds.labels(db_id=db_id).set(freshness)


def _recompute_aggregate_collectors(collectors: _AgnoCollectors, *, db_ids: list[str]) -> None:
    """
    在所有单库指标更新完毕后，重新计算并写入跨库聚合指标（all_daily_* 系列）。

    设计思路：
    - 聚合不在每个 db 刷新时实时累加，而是等所有 db 都完成后从已写入的
      单库 Gauge 中直接读取当前值再求和。这样即使某个 db 刷新失败，
      聚合结果仍反映"已成功刷新的库的最新值之和"，而非中间状态。

    执行步骤：
    1. 遍历所有通用业务指标和 token 指标，对每个指标读取各 db 的当前 Gauge 值求和，
       写入对应的 all_daily_* Gauge。
    2. 清除 all_daily_model_runs 中上一轮的所有时序（防僵尸时序），
       然后对每个 (model_id, provider) 组合跨库求和后写入。

    Args:
        collectors: 指标容器，需已通过 _update_agno_collectors 完成单库写入。
        db_ids    : 参与聚合的数据库 ID 列表（通常等于 state.db_ids）。
    """
    daily_attr_names = [attr_name for _, attr_name in _DAILY_METRIC_FIELDS]
    token_attr_names = [attr_name for _, attr_name in _TOKEN_METRIC_FIELDS]

    # 步骤 1：通用业务指标和 token 指标跨库求和
    # 直接读取已写入的单库 Gauge 内部值（._value.get()），避免重复解析原始数据
    for attr_name in daily_attr_names + token_attr_names:
        total = 0.0
        for db_id in db_ids:
            total += getattr(collectors, attr_name).labels(db_id=db_id)._value.get()
        # all_{attr_name} 是无标签 Gauge，直接 set()
        getattr(collectors, f"all_{attr_name}").set(total)

    # 步骤 2：模型维度聚合（先清理旧时序，再跨库合并）
    # 清除 all_daily_model_runs 上一轮写入的所有 (model_id, provider) 时序
    for model_id, provider in collectors.aggregate_model_series:
        with suppress(KeyError, ValueError):
            collectors.all_daily_model_runs.remove(model_id, provider)
    collectors.aggregate_model_series = set()

    # 跨库累加：同一 (model_id, provider) 在不同 db 的调用次数叠加
    aggregate_counts: dict[tuple[str, str], float] = {}
    for db_id in db_ids:
        for model_id, provider in collectors.model_series_by_db.get(db_id, set()):
            key = (model_id, provider)
            aggregate_counts[key] = aggregate_counts.get(key, 0.0) + collectors.daily_model_runs.labels(
                db_id=db_id, model_id=model_id, provider=provider
            )._value.get()

    # 将聚合结果写入 all_daily_model_runs，并记录标签组合备下次清理
    for (model_id, provider), count in aggregate_counts.items():
        collectors.all_daily_model_runs.labels(model_id=model_id, provider=provider).set(count)
        collectors.aggregate_model_series.add((model_id, provider))


async def _refresh_single_db(
    client: httpx.AsyncClient, *, db_id: str, headers: dict[str, str]
) -> None:
    """
    通知 Agno 后端刷新指定数据库的指标快照（触发型，不返回数据）。

    Args:
        client : 已配置 base_url 的 httpx 异步客户端。
        db_id  : 需要刷新的数据库 ID。
        headers: 含认证信息的请求头。

    Raises:
        httpx.HTTPStatusError: HTTP 响应状态码表示错误时抛出。
    """
    response = await client.post("/metrics/refresh", params={"db_id": db_id}, headers=headers)
    response.raise_for_status()


async def _fetch_single_db_metrics(
    client: httpx.AsyncClient, *, db_id: str, headers: dict[str, str], lookback_days: int
) -> dict[str, Any]:
    """
    从 Agno 后端拉取指定数据库在回溯窗口内的指标数据。

    通常在 _refresh_single_db 之后调用，以获取最新聚合结果。

    Args:
        client       : 已配置 base_url 的 httpx 异步客户端。
        db_id        : 需要查询的数据库 ID。
        headers      : 含认证信息的请求头。
        lookback_days: 回溯天数。

    Returns:
        /metrics 接口返回的 JSON 字典。

    Raises:
        httpx.HTTPStatusError: HTTP 响应状态码表示错误时抛出。
    """
    params = _build_metrics_query_params(lookback_days=lookback_days)
    params["db_id"] = db_id
    response = await client.get("/metrics", params=params, headers=headers)
    response.raise_for_status()
    return response.json()


# =========================================================================== #
# 刷新编排层
# 负责协调多库刷新的顺序、错误隔离和聚合时机，不关心 HTTP 细节。
# 接收函数类型参数（MetricRefresher / MetricFetcher）而非具体的 HTTP 客户端，
# 使核心逻辑与传输实现解耦，便于单元测试时注入 mock。
# =========================================================================== #

async def _refresh_exporter_snapshot(
    *,
    state: _ExporterState,
    collectors: _AgnoCollectors,
    refresh_metrics: MetricRefresher,
    fetch_metrics: MetricFetcher,
) -> None:
    """
    对所有配置的数据库执行一次完整的指标刷新周期，并在末尾重算聚合指标。

    通过 asyncio.Lock 保证同一时刻只有一次刷新在运行；若锁已被持有则直接返回，
    避免 Prometheus 高频抓取时请求堆积。

    刷新流程：
      对每个 db_id：
        1. 触发后端重新聚合（refresh_metrics）
        2. 拉取最新数据（fetch_metrics）
        3. 写入单库 Gauge（_update_agno_collectors）
      所有 db 处理完毕后：
        4. 重算全局聚合指标（_recompute_aggregate_collectors）
        5. 更新 Exporter 元指标

    聚合在步骤 4 集中计算而非逐库累加，确保聚合结果始终基于同一轮刷新的完整数据。
    单个 db 失败不中断其余 db 的刷新，但会标记 exporter_refresh_success = 0。

    Args:
        state          : Exporter 运行时状态。
        collectors     : Prometheus 指标容器。
        refresh_metrics: 触发后端刷新的异步函数（接受 db_id）。
        fetch_metrics  : 拉取后端指标的异步函数（接受 db_id，返回字典）。
    """
    # 若锁已被持有，说明刷新正在进行，直接跳过
    if state.lock.locked():
        return

    async with state.lock:
        state.last_refresh_started_at = time.time()
        state.last_refresh_error = None
        refresh_failed = False

        # 逐库刷新单库指标
        for db_id in state.db_ids:
            try:
                await refresh_metrics(db_id)
                payload = await fetch_metrics(db_id)
                _update_agno_collectors(collectors, db_id=db_id, payload=payload)
                collectors.exporter_db_refresh_success.labels(db_id=db_id).set(1)
            except Exception as exc:  # noqa: BLE001
                refresh_failed = True
                state.last_refresh_error = str(exc)
                collectors.exporter_db_refresh_success.labels(db_id=db_id).set(0)
                collectors.exporter_refresh_errors_total.inc()
                logger.exception(f"Failed to refresh exporter metrics for db_id={db_id}")

        # 所有库刷新完毕后，统一重算全局聚合指标
        state.last_refresh_completed_at = time.time()
        state.last_refresh_duration_s = state.last_refresh_completed_at - state.last_refresh_started_at
        _recompute_aggregate_collectors(collectors, db_ids=state.db_ids)

        # 更新 Exporter 元指标
        collectors.exporter_refresh_success.set(0 if refresh_failed else 1)
        collectors.exporter_refresh_timestamp_seconds.set(state.last_refresh_completed_at)
        collectors.exporter_refresh_duration_seconds.set(state.last_refresh_duration_s)


# =========================================================================== #
# HTTP 组装层
# 负责构造进程内 HTTP 客户端（ASGI Transport）和认证头，
# 将具体的网络操作封装为闭包后注入刷新编排层。
# 这一层存在的意义是隔离"如何发请求"与"如何编排刷新"，
# 使刷新编排层可以在测试中替换为 mock，无需真实网络。
# =========================================================================== #

async def _refresh_exporter_snapshot_via_http(
    *, app: FastAPI, agent_os: Any, state: _ExporterState, collectors: _AgnoCollectors
) -> None:
    """
    使用进程内 HTTP 客户端（ASGI Transport）执行指标刷新。

    通过 httpx.ASGITransport 直接调用 FastAPI 应用，无需建立真实网络连接，
    同时复用应用内已有的认证与路由逻辑。

    refresh_metrics / fetch_metrics 两个闭包定义在此处，是因为它们需要捕获
    async with 块内的 client——client 的生命周期由 async with 管理，
    离开块后连接池即释放，因此闭包只能在块内定义。

    Args:
        app       : 当前 FastAPI 应用实例。
        agent_os  : AgentOS 实例，用于提取认证密钥。
        state     : Exporter 运行时状态。
        collectors: Prometheus 指标容器。
    """
    headers = _build_auth_headers(agent_os)
    # ASGI Transport：在进程内直接调用 FastAPI，避免真实网络开销
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://agno.local", timeout=30.0) as client:
        # 将 HTTP 操作封装为符合类型别名签名的闭包，注入到刷新编排层
        async def refresh_metrics(db_id: str) -> None:
            await _refresh_single_db(client, db_id=db_id, headers=headers)

        async def fetch_metrics(db_id: str) -> dict[str, Any]:
            return await _fetch_single_db_metrics(client, db_id=db_id, headers=headers, lookback_days=state.lookback_days)

        await _refresh_exporter_snapshot(
            state=state,
            collectors=collectors,
            refresh_metrics=refresh_metrics,
            fetch_metrics=fetch_metrics,
        )


# =========================================================================== #
# 调度层
# 决定"是否需要刷新"以及"何时触发刷新"，不关心刷新的具体实现。
# _ensure_metrics_snapshot : 惰性刷新判断，由 /prom-metrics 路由在每次抓取时调用
# setup_prometheus_monitoring: 应用启动入口，完成注册、路由挂载和依赖组装
# =========================================================================== #

async def _ensure_metrics_snapshot(*, state: _ExporterState, refresh_snapshot: SnapshotRefresher) -> None:
    """
    按需触发指标快照刷新（惰性刷新策略）。

    满足以下任一条件时触发：
    - 从未成功刷新过（last_refresh_completed_at == 0）。
    - 距上次刷新完成已超过 refresh_interval_s 秒。

    在 /prom-metrics 被 Prometheus 抓取时调用，实现"拉取驱动"刷新，
    无需独立的后台定时任务。

    Args:
        state           : Exporter 运行时状态。
        refresh_snapshot: 执行实际刷新的异步函数。
    """
    now = time.time()
    is_stale = state.last_refresh_completed_at <= 0 or (now - state.last_refresh_completed_at) >= state.refresh_interval_s
    if not is_stale:
        return
    await refresh_snapshot()


def setup_prometheus_monitoring(
    *,
    app: FastAPI,
    agent_os: Any,
    endpoint: str = "/prom-metrics",
    refresh_interval_s: int = 600,
    lookback_days: int = 2,
    dbs_id: list[str] | None = None,
) -> None:
    """
    初始化并挂载 Prometheus 监控端点到 FastAPI 应用。

    完成以下工作：
    1. 创建独立的 CollectorRegistry，避免污染全局注册表。
    2. 通过 prometheus_fastapi_instrumentator 自动采集 HTTP 请求指标。
    3. 注册所有单库（daily_*）和全局聚合（all_daily_*）的 Gauge/Counter。
    4. 初始化 _ExporterState，管理刷新周期和 db 列表。
    5. 将刷新函数以闭包形式附加到 app.state（便于测试替换和其他路由访问）。
    6. 注册 GET {endpoint} 路由，每次抓取前按需触发惰性刷新，
       然后以 Prometheus 文本格式返回所有指标。

    Args:
        app              : 目标 FastAPI 应用实例。
        agent_os         : AgentOS 实例，提供配置和认证信息。
        endpoint         : Prometheus 抓取端点路径，默认 "/prom-metrics"。
        refresh_interval_s: 两次刷新之间的最小间隔（秒），默认 600。
        lookback_days    : 指标查询回溯天数，默认 2。
        dbs_id           : 需要采集的数据库 ID 列表；为空时记录错误但不中断启动。
    """
    db_ids = [str(db_id) for db_id in (dbs_id or [])]
    if not db_ids:
        logger.error("Monitor missing db ids")

    # 独立 registry，隔离 Agno 指标与其他库的全局指标
    metrics_registry = CollectorRegistry()

    # 自动为所有 HTTP 路由添加请求计数、延迟等标准指标，排除健康检查探针
    Instrumentator(
        excluded_handlers=["/health"],
        should_ignore_untemplated=False,
        should_instrument_requests_inprogress=True,
        should_exclude_streaming_duration=True,
        inprogress_labels=True,
        inprogress_name="agno_http_requests_inprogress",
        registry=metrics_registry,
    ).instrument(app, metric_namespace="agno")

    collectors = _register_agno_collectors(metrics_registry)
    state = _ExporterState(
        refresh_interval_s=int(refresh_interval_s),
        lookback_days=int(lookback_days),
        db_ids=db_ids,
    )

    # 将关键对象挂载到 app.state，便于测试时替换或其他路由访问
    app.state._agno_metrics_registry = metrics_registry
    app.state._agno_metrics_collectors = collectors
    app.state._agno_metrics_state = state
    # 刷新函数封装为闭包，捕获所有依赖，避免全局变量
    app.state._agno_refresh_snapshot = lambda: _refresh_exporter_snapshot_via_http(
        app=app,
        agent_os=agent_os,
        state=state,
        collectors=collectors,
    )

    @app.get(endpoint, include_in_schema=True, tags=["monitoring"])
    async def prom_metrics() -> Response:
        """
        Prometheus 指标抓取端点。

        每次被抓取时：
        1. 检查缓存是否过期（惰性刷新）。
        2. 若过期则触发完整刷新（含单库更新和全局聚合重算）。
        3. 以 Prometheus 文本格式返回所有指标（单库 + 全局聚合 + 元指标）。
        """
        refresh_snapshot = getattr(app.state, "_agno_refresh_snapshot", None)
        if refresh_snapshot is not None:
            await _ensure_metrics_snapshot(state=state, refresh_snapshot=refresh_snapshot)
        return Response(content=generate_latest(metrics_registry), media_type=CONTENT_TYPE_LATEST)

    logger.info(f"Monitor started with {len(db_ids)} db ids")
