# todo 运行时自动执行一次DB初始化并打上日志，和Agent manger保持一致
import asyncio
from typing import List, Optional, Tuple, Union

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from server.data.request_context import resolve_request_user_id
from server.data.data_process.data_preprocessing import (
    cap_outliers_iqr,
    drop_null_columns,
    drop_null_rows,
    fill_null_with_knn,
    fill_null_with_mean,
    fill_null_with_median,
    fill_null_with_value,
    get_dummy_data,
    label_encoding,
    log_transform,
    merge_rare_categories,
    normalize_minmax,
    remove_outliers_iqr,
    sample_rows,
    standard_scaling,
)
from server.data.data_process.task_pool import submit_task

processing_router = APIRouter(prefix="/processing", tags=["Processing"])


class BaseProcessingRequest(BaseModel):
    user_id: Optional[str] = None


class WithColumnsRequest(BaseProcessingRequest):
    columns: Optional[List[str]] = None


class FillNullWithValueRequest(WithColumnsRequest):
    value: Union[int, float, str] = 0


class FillNullWithKnnRequest(WithColumnsRequest):
    n_neighbors: int = 5


class NormalizeMinMaxRequest(WithColumnsRequest):
    feature_range: Tuple[float, float] = (0.0, 1.0)


class MergeRareCategoriesRequest(WithColumnsRequest):
    threshold: float = 0.05
    new_category: str = "Other"


class LogTransformRequest(BaseProcessingRequest):
    columns: List[str]
    add_constant: float = 1.0


class DropNullRowsRequest(WithColumnsRequest):
    pass


class DropNullColumnsRequest(BaseProcessingRequest):
    columns: List[str]


class SampleRowsRequest(BaseProcessingRequest):
    n: Optional[int] = None
    frac: Optional[float] = None
    random_state: Optional[int] = None


class DummyDataRequest(BaseProcessingRequest):
    columns: List[str]
    prefix_sep: str = "_"


class LabelEncodingRequest(BaseProcessingRequest):
    columns: List[str]


class OutliersIQRRequest(WithColumnsRequest):
    threshold: float = 1.5


async def _run_and_summarize(func, *args, **kwargs):
    """
    在通用线程池中执行预处理函数，并返回简要结果摘要。
    """
    try:
        future = submit_task(func, *args, **kwargs)
        df = await asyncio.wrap_future(future)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "user_id": str(args[0]) if args else None,
        "row_count": int(df.shape[0]),
        "columns": list(df.columns),
    }


@processing_router.post("/fill_null/value")
async def api_fill_null_with_value(request: Request, payload: FillNullWithValueRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        fill_null_with_value,
        user_id,
        columns=payload.columns,
        value=payload.value,
    )


@processing_router.post("/fill_null/mean")
async def api_fill_null_with_mean(request: Request, payload: WithColumnsRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        fill_null_with_mean,
        user_id,
        columns=payload.columns,
    )


@processing_router.post("/fill_null/median")
async def api_fill_null_with_median(request: Request, payload: WithColumnsRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        fill_null_with_median,
        user_id,
        columns=payload.columns,
    )


@processing_router.post("/fill_null/knn")
async def api_fill_null_with_knn(request: Request, payload: FillNullWithKnnRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        fill_null_with_knn,
        user_id,
        columns=payload.columns,
        n_neighbors=payload.n_neighbors,
    )


@processing_router.post("/drop_rows/null")
async def api_drop_null_rows(request: Request, payload: DropNullRowsRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        drop_null_rows,
        user_id,
        columns=payload.columns,
    )


@processing_router.post("/drop_columns")
async def api_drop_null_columns(request: Request, payload: DropNullColumnsRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        drop_null_columns,
        user_id,
        columns=payload.columns,
    )


@processing_router.post("/sample_rows")
async def api_sample_rows(request: Request, payload: SampleRowsRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        sample_rows,
        user_id,
        n=payload.n,
        frac=payload.frac,
        random_state=payload.random_state,
    )


@processing_router.post("/get_dummy")
async def api_get_dummy_data(request: Request, payload: DummyDataRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        get_dummy_data,
        user_id,
        columns=payload.columns,
        prefix_sep=payload.prefix_sep,
    )


@processing_router.post("/label_encoding")
async def api_label_encoding(request: Request, payload: LabelEncodingRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        label_encoding,
        user_id,
        columns=payload.columns,
    )


@processing_router.post("/standard_scaling")
async def api_standard_scaling(request: Request, payload: WithColumnsRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        standard_scaling,
        user_id,
        columns=payload.columns,
    )


@processing_router.post("/normalize_minmax")
async def api_normalize_minmax(request: Request, payload: NormalizeMinMaxRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        normalize_minmax,
        user_id,
        columns=payload.columns,
        feature_range=payload.feature_range,
    )


@processing_router.post("/remove_outliers_iqr")
async def api_remove_outliers_iqr(request: Request, payload: OutliersIQRRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        remove_outliers_iqr,
        user_id,
        columns=payload.columns,
        threshold=payload.threshold,
    )


@processing_router.post("/cap_outliers_iqr")
async def api_cap_outliers_iqr(request: Request, payload: OutliersIQRRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        cap_outliers_iqr,
        user_id,
        columns=payload.columns,
        threshold=payload.threshold,
    )


@processing_router.post("/log_transform")
async def api_log_transform(request: Request, payload: LogTransformRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        log_transform,
        user_id,
        columns=payload.columns,
        add_constant=payload.add_constant,
    )


@processing_router.post("/merge_rare_categories")
async def api_merge_rare_categories(request: Request, payload: MergeRareCategoriesRequest):
    user_id = resolve_request_user_id(request, payload.user_id)
    return await _run_and_summarize(
        merge_rare_categories,
        user_id,
        columns=payload.columns,
        threshold=payload.threshold,
        new_category=payload.new_category,
    )

