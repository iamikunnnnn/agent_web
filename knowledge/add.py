from config.db_config import create_knowledge
from knowledge.reader import get_reader
from knowledge.chunk import Chunk

def save_to_knowledge_base(agent_id: str,) -> str:
    """
    用于存储对话中的关键信息到 Chroma 知识库，仅在满足条件时调用：
    1. 信息可复用且事实性；
    2. 信息未存储过或有更新；
    3. 后续对话/任务可能需要用到。
    """
    try:
        knowledge = create_knowledge(id=agent_id,
                                     name=agent_id,
                                     description=f"Knowledge base for {agent_id}")
        # todo 这个方式极其简陋，尽快更改。
        knowledge.insert(path="./docs/knowledge.txt",
                         reader=get_reader(
                             chunker=Chunk.get_chunker("document"))
                         )
        return "成功存储关键信息到知识库"
    except Exception as e:
        return f"存储失败：{str(e)}"

