# Data 系列运行与落盘说明

本文档只描述当前仍在运行的 `data_agent + data-mcp` 链路。

## 结论

- `data` 系列会产生文件。
- 上传的数据文件会落到 `DATA_UPLOAD_DIR` 指向的目录。
- `user_id -> data_path` 映射会写入 `DATA_DB_PATH` 指向的 SQLite。
- 预处理工具会直接覆盖原始 CSV，不会额外生成一个新版本文件。
- 训练工具默认会额外生成 `.joblib` 模型文件。

## 运行链路

1. 用户调用 `data_agent`。
2. Agno run 请求进入主应用。
3. JWT 中间件把鉴权用户写入请求上下文。
4. Agno 的 run 路由优先使用上下文里的 `user_id`。
5. `data_agent` 调用 `data-mcp` 时，`data_mcp_tool` 从 `run_context.user_id` 或 `run_context.metadata.user_id` 取值，并写入请求头。
6. `data-mcp` 路由优先从请求头解析 `user_id`，因此模型不需要再手动填写用户标识。

## 会产生哪些文件

### 1. 上传原始文件

来源：

- `hook/preprocess.py`

行为：

- 用户在 agent run 里上传文件后，文件会被保存到：

```text
${DATA_UPLOAD_DIR}/{user_id}/{原文件名}
```

默认路径：

```text
./user_cache/workspace/{user_id}/...
```

说明：

- 目前按 `user_id` 分目录。
- 文件名保留原始名字。
- 如果同名文件再次上传，会覆盖到同一路径。

### 2. SQLite 元数据

来源：

- `hook/preprocess.py`

行为：

- 每次上传后，会向 SQLite 表 `user_data` 写入或更新：
  - `user_id`
  - `data_path`

默认路径：

```text
${DATA_DB_PATH}
```

默认值：

```text
./user_cache/data/data.db
```

作用：

- 后续所有预处理和训练功能，都是先通过 `user_id` 去这里查 CSV 真实路径。

### 3. 预处理阶段临时文件

来源：

- `server/data/data_process/data_preprocessing.py`

行为：

- 预处理函数会先读取用户当前 CSV。
- 写回时先生成一个同目录临时文件：

```text
{data_path}.tmp
```

- 然后用 `os.replace()` 原子替换原始 CSV。

结果：

- 最终只保留原 CSV 路径上的最新内容。
- `.tmp` 只是短生命周期中间文件，不是长期产物。

### 4. 机器学习模型文件

来源：

- `server/data/machine_learning/machine_learning_model.py`

行为：

- 训练完成后，如果 `save_model=True`，会生成：

```text
{save_dir}/{model_name}_{timestamp}.joblib
```

默认路径：

```text
./user_cache/ml_models/{user_id}
```

说明：

- 默认按 `user_id` 分目录保存。
- `save_dir` 只允许落在 `ML_MODEL_DIR` 根目录之下。
- 如果调用时把 `save_model=False`，则不会落模型文件。

## 各功能是否修改原文件

### 会直接修改原 CSV 的功能

- 缺失值填充
- 删除空值行
- 删除列
- 抽样
- one-hot 编码
- 标签编码
- 标准化
- MinMax 归一化
- IQR 删除异常值
- IQR 截断异常值
- 对数变换
- 合并低频类别

这些操作都会覆盖 `user_data` 当前指向的那份 CSV。

### 不直接修改原 CSV 的功能

- 模型训练本身只读取 CSV

但如果开启模型保存，它会额外产生 `.joblib` 文件。

## 当前风险与限制

### 1. 预处理是覆盖写

- 现在没有版本快照。
- 一旦执行预处理，原 CSV 会被新结果覆盖。

### 2. 同名上传会覆盖

- 上传目录按 `user_id` 隔离，但未自动重命名同名文件。

### 3. 锁是进程内锁

- `data_preprocessing.py` 只对单进程内的同一 `user_id` 做串行保护。
- 如果以后把 `data-mcp` 扩成多副本，需要补跨进程锁或队列。

### 4. 模型目录已做根目录约束

- 当前 `save_dir` 即使由请求指定，也必须位于 `ML_MODEL_DIR` 之下。
- 默认仍建议直接使用系统生成的 `user_cache/ml_models/{user_id}`。

## 当前推荐目录

```text
user_cache/
  data/
    data.db
  workspace/
    {user_id}/
      xxx.csv
      yyy.xlsx
  ml_models/
    {user_id}/
      *.joblib
  office/
    input/
    output/
```
