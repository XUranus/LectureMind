# myapp/management/commands/process_async_tasks.py
"""
Robust async task processor with:
- Concurrency safety (SELECT FOR UPDATE)
- Dependency resolution
- Error isolation
- Comprehensive logging
- Graceful shutdown
"""
import json
import logging
import signal
import sys
import time
import traceback
from typing import Optional
from django.core.management.base import BaseCommand
from django.db import transaction, DatabaseError
from django.utils import timezone
from api.models import AsyncTaskItem
from api.tasks import get_task_function

logger = logging.getLogger('polyu-video')

class Command(BaseCommand):
    help = "Process async video tasks with dependency chaining"
    _shutdown = False

    def handle(self, *args, **options):
        # Setup graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        logger.info("🚀 Async task processor STARTED (Press Ctrl+C to stop)")
        self.stdout.write(self.style.SUCCESS("Async task processor running..."))
        
        while not self._shutdown:
            try:
                processed = self._process_batch()
                if processed == 0:
                    time.sleep(5)  # Reduce DB load when idle
            except Exception as e:
                logger.exception(f"💥 Critical error in processing loop: {e}")
                time.sleep(10)
        
        logger.info("🛑 Async task processor STOPPED gracefully")

    def _handle_shutdown(self, signum, frame):
        logger.info("Received shutdown signal. Stopping after current batch...")
        self._shutdown = True

    def _process_batch(self) -> int:
        """Process one batch of ready tasks. Returns count processed."""
        ready_tasks = self._get_ready_tasks()
        if not ready_tasks:
            return 0

        logger.info(f" Found {len(ready_tasks)} ready task(s) to process")
        processed_count = 0
        
        for task_id in ready_tasks:
            if self._shutdown:
                break
            try:
                self._process_single_task(task_id)
                processed_count += 1
            except Exception as e:
                logger.exception(f"Unhandled exception processing task {task_id}: {e}")
                # Continue to next task - don't let one failure block others
        
        return processed_count

    def _get_ready_tasks(self) -> list:
        """
        Find tasks where:
        - Status is 'pending'
        - AND (no previous task OR previous task status is 'done')
        Returns list of task IDs (minimizes lock time)
        """
        pending_ids = AsyncTaskItem.objects.filter(
            status='pending'
        ).values_list('id', flat=True)
        
        ready_ids = []
        for task_id in pending_ids:
            try:
                if self._is_task_ready(task_id):
                    ready_ids.append(task_id)
            except Exception as e:
                logger.error(f"Error checking readiness for task {task_id}: {e}")
        
        return ready_ids

    def _is_task_ready(self, task_id: str) -> bool:
        """Check if task's dependencies are satisfied (non-atomic check)"""
        try:
            task = AsyncTaskItem.objects.get(id=task_id)
            if not task.previous:
                return True
            
            prev_task = AsyncTaskItem.objects.filter(id=task.previous).first()
            if not prev_task:
                logger.error(f"Task {task_id} references missing previous task {task.previous}")
                return False
            return prev_task.status == 'done'
        except Exception as e:
            logger.error(f"Dependency check failed for task {task_id}: {e}")
            return False

    def _process_single_task(self, task_id: str) -> None:
        """
        Atomically process a single task with full error handling.
        Uses SELECT FOR UPDATE to prevent duplicate processing.
        """
        try:
            with transaction.atomic():
                # Lock task row to prevent duplicate processing
                task = AsyncTaskItem.objects.select_for_update(skip_locked=True).get(id=task_id)
                
                # Re-check status after lock (might have been processed by another worker)
                if task.status != 'pending':
                    logger.debug(f"Task {task_id} no longer pending (status={task.status}), skipping")
                    return
                
                # Verify dependencies again under lock
                if not self._is_task_ready(task_id):
                    logger.warning(f"Task {task_id} dependencies not satisfied after lock, skipping")
                    return
                
                # MARK AS RUNNING
                task.status = 'running'
                task.save(update_fields=['status'])
                logger.info(f"▶️ Started task {task.id} | Func: {task.func_name} | Video: {task.video_id}")

                # PREPARE INPUT
                input_data = self._get_task_input(task)
                
                # EXECUTE TASK FUNCTION
                func = get_task_function(task.func_name)
                start_time = time.time()
                result_data = func(input_data)
                duration = time.time() - start_time
                
                # VALIDATE OUTPUT
                if not isinstance(result_data, dict):
                    raise TypeError(f"Task function must return dict, got {type(result_data)}")
                if 'video_id' not in result_data:
                    logger.warning(f"Task {task.id} result missing 'video_id' (required for chaining)")
                
                # UPDATE SUCCESS
                task.result = json.dumps(result_data)
                task.status = 'done'
                task.finished_at = timezone.now()
                task.save(update_fields=['result', 'status', 'finished_at'])
                
                logger.info(
                    f"✅ Completed task {task.id} | "
                    f"Func: {task.func_name} | "
                    f"Duration: {duration:.2f}s | "
                    f"Video: {task.video_id}"
                )
                
        except AsyncTaskItem.DoesNotExist:
            logger.debug(f"Task {task_id} no longer exists (may have been processed)")
            return
        except Exception as e:
            self._handle_task_error(task_id, e, traceback.format_exc())

    def _get_task_input(self, task: AsyncTaskItem) -> dict:
        """Resolve input: previous task result (if exists) else task.param"""
        if task.previous:
            prev_task = AsyncTaskItem.objects.filter(id=task.previous).first()
            if not prev_task or prev_task.status != 'done':
                raise ValueError(
                    f"Previous task {task.previous} not found or not completed "
                    f"(status={prev_task.status if prev_task else 'MISSING'})"
                )
            try:
                return json.loads(prev_task.result) if prev_task.result else {}
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in previous task result: {e}") from e
        
        try:
            return json.loads(task.param) if task.param else {}
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in task param: {e}") from e

    def _handle_task_error(self, task_id: str, error: Exception, tb: str) -> None:
        """Update task status to 'error' with details"""
        try:
            with transaction.atomic():
                task = AsyncTaskItem.objects.select_for_update().get(id=task_id)
                error_data = {
                    "error": str(error),
                    "error_type": type(error).__name__,
                    "traceback": tb[-2000:]  # Limit size
                }
                task.result = json.dumps(error_data)
                task.status = 'error'
                task.finished_at = timezone.now()
                task.save(update_fields=['result', 'status', 'finished_at'])
                
                logger.error(
                    f"❌ FAILED task {task.id} | "
                    f"Func: {task.func_name} | "
                    f"Error: {type(error).__name__}: {error} | "
                    f"Video: {task.video_id}"
                )
        except Exception as e:
            logger.critical(f"CRITICAL: Could not update error state for task {task_id}: {e}")