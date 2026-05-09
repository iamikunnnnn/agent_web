"""
Knowledge Base File Processor

Handles asynchronous file processing for knowledge bases.
Uses asyncio for background task processing.
"""

import asyncio
import logging
from typing import Dict, Set
from datetime import datetime, timezone

from auth.knowledge_db import (
    get_file_record,
    update_file_status,
    update_kb_chunk_count,
    update_kb_indexing_status,
    get_knowledge_base,
)

from config.db_config import create_knowledge
from knowledge.chunk import Chunk
from knowledge.reader import get_reader

logger = logging.getLogger(__name__)


class FileProcessor:
    """
    Asynchronous file processor for knowledge bases.

    Uses an asyncio queue to process files in the background.
    """

    def __init__(self, max_workers: int = 3):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.workers: Set[asyncio.Task] = set()
        self.max_workers = max_workers
        self.running = False
        self.processing: Set[str] = set()  # Track currently processing file IDs

    async def start(self):
        """Start the background workers."""
        if self.running:
            return

        self.running = True
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.add(worker)
            worker.add_done_callback(self.workers.discard)

        logger.info(f"Started {self.max_workers} file processing workers")

    async def stop(self):
        """Stop the background workers."""
        self.running = False
        for _ in range(self.max_workers):
            await self.queue.put(None)  # Send stop signal

        await asyncio.gather(*self.workers, return_exceptions=True)
        logger.info("Stopped file processing workers")

    async def enqueue(self, file_id: str, kb_id: str):
        """Enqueue a file for processing."""
        await self.queue.put((file_id, kb_id))
        logger.info(f"Enqueued file {file_id} for processing in KB {kb_id}")

    async def _worker(self, name: str):
        """Worker coroutine that processes files from the queue."""
        logger.info(f"Worker {name} started")

        while self.running:
            try:
                item = await self.queue.get()

                # Check for stop signal
                if item is None:
                    break

                file_id, kb_id = item

                # Skip if already processing
                if file_id in self.processing:
                    self.queue.task_done()
                    continue

                self.processing.add(file_id)
                await self._process_file(file_id, kb_id, name)
                self.processing.discard(file_id)

                self.queue.task_done()

            except Exception as e:
                logger.error(f"Worker {name} error: {e}", exc_info=True)
                self.queue.task_done()

        logger.info(f"Worker {name} stopped")

    async def _process_file(self, file_id: str, kb_id: str, worker_name: str):
        """Process a single file."""
        logger.info(f"Worker {worker_name} processing file {file_id}")

        try:
            # Update status to processing
            update_file_status(file_id, "processing")

            # Get file record
            file_record = get_file_record(file_id)
            if not file_record:
                logger.error(f"File {file_id} not found")
                return

            # Get knowledge base
            kb = get_knowledge_base(kb_id)
            if not kb:
                logger.error(f"Knowledge base {kb_id} not found")
                update_file_status(file_id, "failed", error_message="Knowledge base not found")
                return

            # Create knowledge instance
            safe_kb_id = kb_id.replace("-", "_")
            knowledge = create_knowledge(
                id=safe_kb_id,
                name=kb.kb_name,
                description=kb.kb_description,
            )

            # Use FileDetector to automatically select reader and chunker based on file type
            # This ensures optimal processing for each file type without user selection
            from knowledge.file_detector import get_reader_and_chunker
            reader, chunker = get_reader_and_chunker(
                file_record.file_path,
                chunk_size=kb.chunk_size,
                overlap=kb.chunk_overlap,
            )

            logger.info(f"Worker {worker_name} using chunker: {type(chunker).__name__} for {file_record.file_path}")

            # Update knowledge index status
            update_kb_indexing_status(kb_id, "indexing")

            # Insert file into knowledge base with auto-selected reader and chunker
            knowledge.insert(
                path=file_record.file_path,
                reader=reader,
            )

            # Update status to completed
            update_file_status(file_id, "completed")

            # Update KB chunk count
            chunk_count = await self._count_chunks(kb.vector_table_name)
            update_kb_chunk_count(kb_id, increment=chunk_count)
            update_kb_indexing_status(kb_id, "idle")

            logger.info(f"Worker {worker_name} completed file {file_id} with {chunk_count} chunks")

        except Exception as e:
            logger.error(f"Worker {worker_name} failed to process file {file_id}: {e}", exc_info=True)
            update_file_status(file_id, "failed", error_message=str(e))
            update_kb_indexing_status(kb_id, "failed")

    async def _count_chunks(self, vector_table_name: str) -> int:
        """Count chunks in a vector table."""
        try:
            import psycopg
            from config.db_config import Config, get_psycopg_db_url

            with psycopg.connect(get_psycopg_db_url(id="knowledge-processor")) as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) FROM {Config.DB_NAME}.{vector_table_name}")
                    count = cur.fetchone()[0]
                    return count
        except Exception as e:
            logger.error(f"Failed to count chunks in {vector_table_name}: {e}")
            return 0


# Global file processor instance
_file_processor: FileProcessor = None


def get_file_processor() -> FileProcessor:
    """Get the global file processor instance."""
    global _file_processor
    if _file_processor is None:
        _file_processor = FileProcessor(max_workers=3)
    return _file_processor


async def start_file_processor():
    """Start the global file processor."""
    processor = get_file_processor()
    await processor.start()


async def stop_file_processor():
    """Stop the global file processor."""
    processor = get_file_processor()
    await processor.stop()


async def queue_file_for_processing(file_id: str, kb_id: str):
    """Queue a file for processing."""
    processor = get_file_processor()
    await processor.enqueue(file_id, kb_id)


# Utility functions for manual processing

async def process_file_sync(file_id: str, kb_id: str):
    """
    Synchronously process a file (for testing or immediate processing).

    This function blocks until processing is complete.
    """
    processor = FileProcessor(max_workers=1)
    await processor.start()
    await processor.enqueue(file_id, kb_id)
    await processor.queue.join()
    await processor.stop()

    # Get final status
    file_record = get_file_record(file_id)
    return file_record.processing_status if file_record else "failed"


def sync_process_file(file_id: str, kb_id: str) -> str:
    """
    Synchronous wrapper for file processing (for use in non-async contexts).

    Returns the final processing status.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(process_file_sync(file_id, kb_id))
