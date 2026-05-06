# todo 待agno完善component的save功能后尝试把model的设置也迁移到component。

import os
from typing import Optional

from agno.knowledge.embedder.azure_openai import AzureOpenAIEmbedder
from agno.models.base import Model
from agno.models.openai import OpenAILike
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class Config:
    """应用配置管理类"""


    SILICONFLOW_API_KEY: Optional[str] = os.getenv("SILICONFLOW_API_KEY")
    SILICONFLOW_MODEL_ID: Optional[str] = os.getenv("SILICONFLOW_MODEL_ID")
    SILICONFLOW_BESE_URL: Optional[str] = os.getenv("SILICONFLOW_BESE_URL")

    AZURE_EMBEDDER_OPENAI_API_KEY: Optional[str] = os.getenv("AZURE_EMBEDDER_OPENAI_API_KEY")
    AZURE_EMBEDDER_OPENAI_ENDPOINT: Optional[str] = os.getenv("AZURE_EMBEDDER_OPENAI_ENDPOINT")
    AZURE_EMBEDDER_OPENAI_API_VERSION: Optional[str] = os.getenv("AZURE_EMBEDDER_OPENAI_API_VERSION")
    AZURE_EMBEDDER_DEPLOYMENT: Optional[str] = os.getenv("AZURE_EMBEDDER_DEPLOYMENT")
    @classmethod
    def validate_config(cls) -> bool:
        """验证必要的配置是否存在"""
        # 验证SILICONFLOW配置
        if not cls.SILICONFLOW_API_KEY:
            print("❌ 缺少必要的环境变量: SILICONFLOW_API_KEY")
            return False

        if not cls.SILICONFLOW_MODEL_ID:
            print("❌ 缺少必要的环境变量: SILICONFLOW_MODEL_ID")
            return False
    @classmethod
    def get_siliconflow_config(cls, id=None) -> dict:
        """获取Azure OpenAI配置字典"""
        model_id = id if id else cls.SILICONFLOW_MODEL_ID
        return {
            "id": model_id,
            "api_key": cls.SILICONFLOW_API_KEY,
            "base_url": cls.SILICONFLOW_BESE_URL
        }

    # todo 添加硅基流动的embedder model
    @classmethod
    def get_azure_embedder_config(cls, id=None) -> dict:
        """获取Azure Embedder配置字典"""
        model_id = id if id else cls.AZURE_EMBEDDER_DEPLOYMENT
        return {
            "id": model_id,
            "api_key": cls.AZURE_EMBEDDER_OPENAI_API_KEY,
            "api_version": cls.AZURE_EMBEDDER_OPENAI_API_VERSION,
            "azure_endpoint": cls.AZURE_EMBEDDER_OPENAI_ENDPOINT,
        }
    @classmethod
    def get_browser_use_config(cls, id=None) -> dict:
        model_id = id if id else cls.SILICONFLOW_MODEL_ID
        return {
            "model":model_id,
            "api_key": cls.SILICONFLOW_API_KEY,
            "base_url": cls.SILICONFLOW_BESE_URL
        }
def get_ai_model(model_id=None, model_type="siliconflow") -> Model:
    """
    获取AI模型实例

    Args:
        model_id: 模型ID，如不指定则使用默认配置
        model_type: 模型类型，支持 "deepseek" 或 "azure"

    Returns:
        模型实例
    """
    if model_type.lower() == "siliconflow":
        config = Config.get_siliconflow_config(model_id)
        return OpenAILike(**config)
        # config = Config.get_new_version_azure_openai_config(model_id)
        # return OpenAIChat(**config)
    else:
        print("目前仅支持siliconflow_type，已自动使用siliconflow")
        config = Config.get_siliconflow_config(model_id)
        return OpenAILike(**config)
def get_azure_embedder(id=None) -> AzureOpenAIEmbedder:
    """
    获取Azure Embedder实例

    Args:
        id: 模型ID，如不指定则使用默认配置

    Returns:
        AzureOpenAIEmbedder实例
    """
    config = Config.get_azure_embedder_config(id)
    return AzureOpenAIEmbedder(**config)
