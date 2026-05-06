import asyncio
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.data.machine_learning.process_pool import submit_train_task

ml_router = APIRouter(prefix="/ml", tags=["Machine_Learning"])


class TrainModelRequest(BaseModel):
    user_id: str
    model_name: str
    X_columns: List[str]
    y_column: Union[str, List[str]]
    mode: str
    model_param: Optional[Dict[str, Any]] = None
    test_size: float = 0.2
    random_state: int = 42
    use_bayes_search: bool = False
    bayes_iter: int = 5
    save_dir: str = "./user_cache/ml_models"
    save_model: bool = True


@ml_router.post("/train")
async def api_train_model(payload: TrainModelRequest):
    """
    训练模型
    """
    try:
        future = submit_train_task(
            user_id=payload.user_id,
            model_name=payload.model_name,
            X_columns=payload.X_columns,
            y_column=payload.y_column,
            mode=payload.mode,
            model_param=payload.model_param,
            test_size=payload.test_size,
            random_state=payload.random_state,
            use_bayes_search=payload.use_bayes_search,
            bayes_iter=payload.bayes_iter,
            save_dir=payload.save_dir,
            save_model=payload.save_model,
        )
        result = await asyncio.wrap_future(future)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return result
