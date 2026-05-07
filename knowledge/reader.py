
from agno.knowledge.reader.docling_reader import DoclingReader
def get_reader(chunker) -> DoclingReader:
    if chunker is None:
        raise Exception('chunk is None,can`t create DoclingReader')
    reader = DoclingReader(chunking_strategy=chunker)
    return reader