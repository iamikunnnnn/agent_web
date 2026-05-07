from agno.knowledge.chunking.document import DocumentChunking
from agno.knowledge.chunking.fixed import FixedSizeChunking
from agno.knowledge.chunking.semantic import SemanticChunking
class Chunk:
    def __init__(self,mode:str,chunk_size:int =5000,overlap:int = 200, **kwargs):
        self.mode = mode
        self.chunk_size = chunk_size
        self.overlap = overlap
    @staticmethod
    def get_chunker(self, **kwargs):
        if self.mode == 'fixed':
            chunker =FixedSizeChunking(**kwargs)
        elif self.mode == 'semantic':
            chunker =SemanticChunking(**kwargs)
        elif self.mode == 'document':
            chunker=DocumentChunking(**kwargs)
        else:
            chunker = DocumentChunking(**kwargs)
        return chunker

