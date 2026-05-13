# todo 待agno完善component的save功能后尝试把model的设置也迁移到component。

import os
from typing import Optional

from agno.knowledge.embedder.openai_like import OpenAILikeEmbedder
from agno.models.base import Model
from agno.models.openai import OpenAILike
from agno.models.deepseek import DeepSeek
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class Config:
    """应用配置管理类"""

    # SiliconFlow 配置
    SILICONFLOW_API_KEY: Optional[str] = os.getenv("SILICONFLOW_API_KEY")
    SILICONFLOW_MODEL_ID: Optional[str] = os.getenv("SILICONFLOW_MODEL_ID")
    SILICONFLOW_BESE_URL: Optional[str] = os.getenv("SILICONFLOW_BESE_URL")

    # DeepSeek 配置
    DEEPSEEK_API_KEY: Optional[str] = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL_ID: Optional[str] = os.getenv("DEEPSEEK_MODEL_ID", "deepseek-chat")
    DEEPSEEK_BASE_URL: Optional[str] = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    # siliconflow Embedder 配置
    SILICONFLOW_EMBEDDER_OPENAI_API_KEY: Optional[str] = os.getenv("SILICONFLOW_EMBEDDER_OPENAI_API_KEY")
    SILICONFLOW_EMBEDDER_OPENAI_ENDPOINT: Optional[str] = os.getenv("SILICONFLOW_EMBEDDER_OPENAI_ENDPOINT")
    SILICONFLOW_EMBEDDER_MODEL_ID: Optional[str] = os.getenv("SILICONFLOW_EMBEDDER_MODEL_ID")

    @classmethod
    def validate_config(cls) -> bool:
        """验证必要的配置是否存在"""

        # 验证 SiliconFlow 配置
        if not cls.SILICONFLOW_API_KEY:
            print("❌ 缺少必要的环境变量: SILICONFLOW_API_KEY")
            return False

        if not cls.SILICONFLOW_MODEL_ID:
            print("❌ 缺少必要的环境变量: SILICONFLOW_MODEL_ID")
            return False

        if not cls.SILICONFLOW_BESE_URL:
            print("❌ 缺少必要的环境变量: SILICONFLOW_BESE_URL")
            return False

        return True

    @classmethod
    def get_siliconflow_config(cls, id=None) -> dict:
        """获取 SiliconFlow 配置字典"""
        model_id = id if id else cls.SILICONFLOW_MODEL_ID
        return {
            "id": model_id,
            "api_key": cls.SILICONFLOW_API_KEY,
            "base_url": cls.SILICONFLOW_BESE_URL,
        }

    @classmethod
    def get_deepseek_config(cls, id=None) -> dict:
        """获取 DeepSeek 配置字典"""
        model_id = id if id else cls.DEEPSEEK_MODEL_ID
        return {
            "id": model_id,
            "api_key": cls.DEEPSEEK_API_KEY,
            "base_url": cls.DEEPSEEK_BASE_URL,
        }

    # todo 添加硅基流动的embedder model
    @classmethod
    def get_siliconflow_embedder_config(cls, id=None) -> dict:
        """获取 siliconflow Embedder 配置字典"""
        model_id = id if id else cls.SILICONFLOW_EMBEDDER_MODEL_ID
        return {
            "id": model_id,
            "api_key": cls.SILICONFLOW_EMBEDDER_OPENAI_API_KEY,
            "base_url": cls.SILICONFLOW_EMBEDDER_OPENAI_ENDPOINT,
        }

    @classmethod
    def get_browser_use_config(cls, id=None) -> dict:
        model_id = id if id else cls.SILICONFLOW_MODEL_ID
        return {
            "model": model_id,
            "api_key": cls.SILICONFLOW_API_KEY,
            "base_url": cls.SILICONFLOW_BESE_URL,
        }


def get_ai_model(model_id=None, model_type="deepseek") -> Model:
    """
    获取AI模型实例

    Args:
        model_id: 模型ID，如不指定则使用默认配置
        model_type: 模型类型，支持 "siliconflow" 或 "deepseek"

    Returns:
        模型实例
    """
    if model_type.lower() == "siliconflow":
        config = Config.get_siliconflow_config(model_id)
        return OpenAILike(**config)

    elif model_type.lower() == "deepseek":
        config = Config.get_deepseek_config(model_id)
        return DeepSeek(**config)

    else:
        print("目前仅支持 siliconflow / deepseek，已自动使用 siliconflow")
        config = Config.get_siliconflow_config(model_id)
        return OpenAILike(**config)


def get_siliconflow_embedder(id=None) -> OpenAILikeEmbedder:
    """
    获取siliconflow Embedder实例

    Args:
        id: 模型ID，如不指定则使用默认配置

    Returns:
        siliconflowOpenAIEmbedder实例
    """
    config = Config.get_siliconflow_embedder_config(id)
    return OpenAILikeEmbedder(**config)