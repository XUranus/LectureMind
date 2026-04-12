"""
Robust async task processor with:
- .env file auto-loading
- Concurrency safety (SELECT FOR UPDATE)
- Dependency resolution with cascade failure
- Error isolation
- Comprehensive logging
- Graceful shutdown
"""
import json
import logging
import os
import signal
import sys
import time
import traceback
from pathlib import Path
from typing import Optional
from django.core.management.base import BaseCommand
from django.db import transaction, DatabaseError
from django.utils import timezone
from api.models import AsyncTaskItem
from api.tasks import get_task_function

logger = logging.getLogger('LectureMind')


def load_dotenv_file():
    """Load .env file from project root (same level as .gitignore)."""
    # Walk up from manage.py dir to find .env
    search = Path(__file__).resolve().parent
    for _ in range(10):
        env_file = search / '.env'
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' not in line:
                        continue
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    # Handle inline comments (only after space+hash)
                    if ' #' in val:
                        val = val.split(' #')[0].strip().strip("'").strip('"')
                    if key not in os.environ:  # Don't override existing env
                        os.environ[key] = val
            logger.info(f"Loaded .env from {env_file}")
            return
        search = search.parent
    logger.warning("No .env file found in parent directories")


class Command(BaseCommand):
    help = "Process async video tasks with dependency chaining"
    _shutdown = False

    def handle(self, *args, **options):
        load_dotenv_file()

        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        logger.info("Async task processor STARTED (Press Ctrl+C to stop)")
        self.stdout.write(self.style.SUCCESS("Async task processor running..."))

        while not self._shutdown:
            try:
                processed = self._process_batch()
                if processed == 0:
                    time.sleep(5)
            except Exception as e:
                logger.exception(f"Critical error in processing loop: {e}")
                time.sleep(10)

        logger.info("Async task processor STOPPED gracefully")

    def _handle_shutdown(self, signum, frame):
        logger.info("Received shutdown signal. Stopping after current batch...")
        self._shutdown = True

    def _process_batch(self) -> int:
        """Process one batch of ready tasks. Returns count processed."""
        ready_tasks = self._get_ready_tasks()
        if not ready_tasks:
            return 0

        logger.info(f"Found {len(ready_tasks)} ready task(s) to process")
        processed_count = 0

        for task_id in ready_tasks:
            if self._shutdown:
                break
            try:
                self._process_single_task(task_id)
                processed_count += 1
            except Exception as e:
                logger.exception(f"Unhandled exception processing task {task_id}: {e}")

        return processed_count

    def _get_ready_tasks(self) -> list:
        """Find pending tasks whose dependencies are satisfied."""
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
        """Check if task's dependencies are satisfied."""
        try:
            task = AsyncTaskItem.objects.get(id=task_id)
            if not task.previous:
                return True

            prev_task = AsyncTaskItem.objects.filter(id=task.previous).first()
            if not prev_task:
                logger.error(f"Task {task_id} references missing previous task {task.previous}")
                return False

            # If predecessor failed, cascade failure to this task
            if prev_task.status == 'error':
                self._cascade_failure(task, prev_task)
                return False

            return prev_task.status == 'done'
        except Exception as e:
            logger.error(f"Dependency check failed for task {task_id}: {e}")
            return False

    def _cascade_failure(self, task: AsyncTaskItem, failed_predecessor: AsyncTaskItem):
        """Mark a task as failed because its predecessor failed."""
        error_data = {
            "error": f"Predecessor task '{failed_predecessor.title}' failed",
            "error_type": "CascadeFailure",
            "predecessor_id": str(failed_predecessor.id),
            "predecessor_func": failed_predecessor.func_name,
        }
        # Try to extract the original error from predecessor
        try:
            pred_result = json.loads(failed_predecessor.result) if failed_predecessor.result else {}
            error_data["original_error"] = pred_result.get("error", "Unknown error")
        except (json.JSONDecodeError, AttributeError):
            pass

        task.result = json.dumps(error_data)
        task.status = 'error'
        task.finished_at = timezone.now()
        task.save(update_fields=['result', 'status', 'finished_at'])
        logger.warning(
            f"CASCADE FAIL task {task.id} ({task.func_name}) "
            f"<- predecessor {failed_predecessor.id} ({failed_predecessor.func_name})"
        )

    def _process_single_task(self, task_id: str) -> None:
        """
        Process a single task using three separate transactions so that the
        'running' status and incremental progress updates are immediately
        visible to other readers (e.g. the REST API).

        Phase 1 (atomic): Claim the task — pending → running. Commits right
                          away so the API can see 'running' immediately.
        Phase 2 (no tx):  Execute the task function. _report_progress() does
                          plain UPDATE calls that commit on their own, so the
                          frontend sees live progress percentages.
        Phase 3 (atomic): Finalise — running → done/error.
        """
        # ── Phase 1: Claim the task ──────────────────────────────────────────
        try:
            with transaction.atomic():
                task = AsyncTaskItem.objects.select_for_update(skip_locked=True).get(id=task_id)

                if task.status != 'pending':
                    return

                if not self._is_task_ready(task_id):
                    return

                input_data = self._get_task_input(task)
                func = get_task_function(task.func_name)

                task.status = 'running'
                task.progress = 0
                task.save(update_fields=['status', 'progress'])
                logger.info(f"STARTED task {task.id} | Func: {task.func_name} | Video: {task.video_id}")
                # Transaction commits here — 'running' is now visible externally.

        except AsyncTaskItem.DoesNotExist:
            return
        except Exception as e:
            self._handle_task_error(task_id, e, traceback.format_exc())
            return

        # ── Phase 2: Execute the task (outside any transaction) ─────────────
        result_data = None
        exec_error = None
        exec_tb = None
        start_time = time.time()
        try:
            result_data = func(input_data)
            duration = time.time() - start_time

            if not isinstance(result_data, dict):
                raise TypeError(f"Task function must return dict, got {type(result_data)}")

            logger.info(
                f"COMPLETED task {task_id} | Func: {task.func_name} | "
                f"Duration: {duration:.2f}s | Video: {task.video_id}"
            )
        except Exception as e:
            exec_error = e
            exec_tb = traceback.format_exc()

        # ── Phase 3: Finalise ────────────────────────────────────────────────
        if exec_error is not None:
            self._handle_task_error(task_id, exec_error, exec_tb)
        else:
            try:
                with transaction.atomic():
                    task = AsyncTaskItem.objects.select_for_update().get(id=task_id)
                    task.result = json.dumps(result_data)
                    task.status = 'done'
                    task.progress = 100
                    task.finished_at = timezone.now()
                    task.save(update_fields=['result', 'status', 'progress', 'finished_at'])
            except Exception as e:
                logger.critical(f"CRITICAL: Could not finalise task {task_id}: {e}")

    def _get_task_input(self, task: AsyncTaskItem) -> dict:
        """Resolve input: previous task result (if exists) else task.param."""
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
        """Update task status to 'error' with details."""
        try:
            with transaction.atomic():
                task = AsyncTaskItem.objects.select_for_update().get(id=task_id)
                error_data = {
                    "error": str(error),
                    "error_type": type(error).__name__,
                    "traceback": tb[-2000:]
                }
                task.result = json.dumps(error_data)
                task.status = 'error'
                task.finished_at = timezone.now()
                task.save(update_fields=['result', 'status', 'finished_at'])

                logger.error(
                    f"FAILED task {task.id} | Func: {task.func_name} | "
                    f"Error: {type(error).__name__}: {error} | Video: {task.video_id}"
                )
        except Exception as e:
            logger.critical(f"CRITICAL: Could not update error state for task {task_id}: {e}")
