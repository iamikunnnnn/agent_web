 知识库添加流程

  完整流程图

  用户上传文件
      │
      ├─ POST /knowledge/bases/{kb_id}/files (api/knowledge_router.py)
      │
      ├─ 1. 检查权限
      │   └─ 检查用户是否有该 KB 的写入权限
      │
      ├─ 2. 上传到七牛云存储
      │   └─ storage.upload_content() → 返回 URL
      │
      ├─ 3. 创建文件记录 (auth/knowledge_db.py)
      │   └─ create_file_record(kb_id, file_name, file_url, ...)
      │
      ├─ 4. 更新文件计数
      │   └─ update_kb_file_count(kb_id, +1)
      │
      ├─ 5. 队列处理 (auth/knowledge_processor.py)
      │   └─ queue_file_for_processing(file_id, kb_id)
      │       └─ FileProcessor.enqueue((file_id, kb_id))
      │
      └─ 6. 后台处理 (异步)
          │
          ├─ Worker 从队列取任务
          │   └─ await queue.get() → (file_id, kb_id)
          │
          ├─ 更新状态为 "processing"
          │   └─ update_file_status(file_id, "processing")
          │
          ├─ 创建 Knowledge 实例
          │   └─ create_knowledge(id=safe_kb_id, name=kb_name, ...)
          │
          ├─ 获取文件（从 URL 或本地路径）
          │   └─ _download_file_to_temp() 如果是 URL
          │
          ├─ 自动选择 Reader 和 Chunker ⭐
          │   └─ get_reader_and_chunker(file_path, chunk_size, overlap)
          │       │
          │       ├─ 文件类型检测：FileDetector.detect_file_type()
          │       │   └─ 根据扩展名映射到 FileType
          │       │
          │       ├─ 选择 Reader：READER_FACTORY_MAP[file_type]
          │       │   └─ PDFReader, CSVReader, DocxReader, ...
          │       │
          │       └─ 选择 Chunker：RECOMMENDED_CHUNKER_MAP[file_type]
          │           └─ DocumentChunking, RowChunking, ...
          │
          ├─ 更新 KB 状态为 "indexing"
          │   └─ update_kb_indexing_status(kb_id, "indexing")
          │
          ├─ 插入知识库 (Agno API)
          │   └─ knowledge.insert(path=file_path, reader=reader)
          │       └─ Agno 内部：读取文件 → chunk → 向量化 → 存储
          │
          ├─ 更新状态为 "completed"
          │   └─ update_file_status(file_id, "completed")
          │
          ├─ 统计 chunk 数量
          │   └─ _count_chunks(vector_table_name)
          │   └─ SELECT COUNT(*) FROM {schema}.{vector_table}
          │
          ├─ 更新 KB chunk 计数
          │   └─ update_kb_chunk_count(kb_id, increment=chunk_count)
          │
          └─ 更新 KB 状态为 "idle"
              └─ update_kb_indexing_status(kb_id, "idle")
          │
          └─ 清理临时文件
              └─ temp_file.unlink()