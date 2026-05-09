"""
Pydantic models for knowledge base API.

Note: Chunking strategy is now automatically selected based on file type.
Users cannot override this selection - the system uses FileDetector to
choose the optimal reader and chunker for each file.
"""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="知识库名称")
    description: str = Field(default="", max_length=500, description="知识库描述")
    max_results: int = Field(default=10, ge=1, le=50, description="搜索最大结果数")
    is_public: bool = Field(default=False, description="是否公开")


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="知识库名称")
    description: Optional[str] = Field(None, max_length=500, description="知识库描述")
    max_results: Optional[int] = Field(None, ge=1, le=50, description="搜索最大结果数")
    is_public: Optional[bool] = Field(None, description="是否公开")
    is_active: Optional[bool] = Field(None, description="是否激活")


class KnowledgeBaseResponse(BaseModel):
    kb_id: str = Field(..., description="知识库ID")
    name: str = Field(..., description="知识库名称")
    description: str = Field(..., description="知识库描述")
    owner_id: str = Field(..., description="所有者ID")
    is_official: bool = Field(..., description="是否为官方知识库")
    is_public: bool = Field(..., description="是否公开")
    max_results: int = Field(..., description="搜索最大结果数")
    file_count: int = Field(..., description="文件数量")
    total_chunks: int = Field(..., description="总块数")
    is_active: bool = Field(..., description="是否激活")
    indexing_status: str = Field(..., description="索引状态")
    last_indexed_at: Optional[datetime] = Field(None, description="最后索引时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class FileUploadResponse(BaseModel):
    file_id: str = Field(..., description="文件ID")
    file_name: str = Field(..., description="文件名")
    kb_id: str = Field(..., description="知识库ID")
    processing_status: str = Field(..., description="处理状态")
    uploaded_at: datetime = Field(..., description="上传时间")

    class Config:
        from_attributes = True


class FileResponse(BaseModel):
    file_id: str = Field(..., description="文件ID")
    kb_id: str = Field(..., description="知识库ID")
    file_name: str = Field(..., description="文件名")
    file_size: int = Field(..., description="文件大小(字节)")
    file_type: str = Field(..., description="文件类型")
    processing_status: str = Field(..., description="处理状态")
    chunk_count: int = Field(..., description="分块数量")
    error_message: Optional[str] = Field(None, description="错误信息")
    uploaded_at: datetime = Field(..., description="上传时间")
    processed_at: Optional[datetime] = Field(None, description="处理完成时间")

    class Config:
        from_attributes = True


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="搜索查询")
    kb_id: str = Field(..., description="知识库ID")
    max_results: int = Field(default=10, ge=1, le=50, description="最大结果数")


class SearchResult(BaseModel):
    content: str = Field(..., description="内容")
    metadata: dict = Field(..., description="元数据")
    score: float = Field(..., description="相似度分数")
    source_file: Optional[str] = Field(None, description="来源文件")


class CopyKnowledgeRequest(BaseModel):
    source_kb_id: str = Field(..., description="源知识库ID(必须为官方知识库)")


class CopyKnowledgeResponse(BaseModel):
    copy_id: str = Field(..., description="复制记录ID")
    source_kb_id: str = Field(..., description="源知识库ID")
    target_kb_id: str = Field(..., description="目标知识库ID")
    chunks_copied: int = Field(..., description="复制的块数")
    copied_at: datetime = Field(..., description="复制时间")
