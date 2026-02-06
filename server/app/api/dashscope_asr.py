"""
Module for asynchronous speech-to-text transcription using Alibaba Cloud DashScope's
`qwen3-asr-flash-filetrans` model.

This module provides:
- Submission of audio files for transcription
- Polling for task status
- Retrieval of final transcript with sentence-level timestamps
- Configurable region (Beijing vs. Singapore)

Author: Your Name
"""

import os
import time
import json
import logging
from typing import Optional, Dict, Any, List, Literal
from urllib.parse import urljoin
import requests

# Configure module logger
logger = logging.getLogger(__name__)


class DashScopeASRClient:
    """
    A client for interacting with Alibaba Cloud DashScope's ASR service using the
    `qwen3-asr-flash-filetrans` model.

    Attributes:
        api_key (str): The DashScope API key for authentication.
        base_url (str): Base URL for the DashScope API (region-specific).
        poll_interval (float): Interval in seconds between polling attempts.
        max_retries (int): Maximum number of retries for transient errors.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        region: Literal["beijing", "singapore"] = "beijing",
        poll_interval: float = 2.0,
        max_retries: int = 3,
    ):
        """
        Initialize the DashScope ASR client.

        Args:
            api_key: DashScope API key. If not provided, reads from env var `DASHSCOPE_API_KEY`.
            region: Target region for API calls. Either "beijing" or "singapore".
            poll_interval: Seconds to wait between polling task status.
            max_retries: Max retry attempts for HTTP requests (for idempotent operations).

        Raises:
            ValueError: If API key is not provided and not found in environment.
        """
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key must be provided via argument or DASHSCOPE_API_KEY environment variable."
            )

        if region == "beijing":
            self.base_url = "https://dashscope.aliyuncs.com"
        elif region == "singapore":
            self.base_url = "https://dashscope-intl.aliyuncs.com"
        else:
            raise ValueError("Region must be 'beijing' or 'singapore'.")

        self.poll_interval = poll_interval
        self.max_retries = max_retries

        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }


    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        """
        Make an HTTP request with retry logic and error handling.

        Args:
            method: HTTP method ('GET', 'POST', etc.)
            url: Full URL to request
            **kwargs: Additional arguments passed to requests.request

        Returns:
            requests.Response: The HTTP response.

        Raises:
            requests.RequestException: After max retries or on non-retryable errors.
        """
        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.request(method, url, headers=self._headers, **kwargs)
                if response.status_code < 500:
                    return response
                logger.warning(f"Server error (attempt {attempt}/{self.max_retries}): {response.status_code}")
            except requests.RequestException as e:
                last_exception = e
                logger.warning(f"Request failed (attempt {attempt}/{self.max_retries}): {e}")

            if attempt < self.max_retries:
                time.sleep(self.poll_interval)

        if last_exception:
            raise last_exception
        else:
            # This should not happen, but satisfy type checker
            raise requests.RequestException("Unexpected request failure after retries")


    def _make_unauthenticated_request(self, url: str) -> requests.Response:
        """Make a GET request without any authentication headers (for pre-signed URLs)."""
        response = requests.get(url)
        return response


    def submit_transcription_task(
        self,
        file_url: str,
        language: str = "en",
        channel_id: List[int] = [0],
        enable_itn: bool = False,
    ) -> str:
        """
        Submit an asynchronous transcription task.

        Args:
            file_url: Publicly accessible URL to the audio file (WAV/PCM recommended).
            language: Language code (e.g., 'en', 'zh').
            channel_id: List of audio channels to transcribe (default: [0]).
            enable_itn: Enable inverse text normalization (e.g., '123' → 'one hundred twenty-three').

        Returns:
            str: The task ID assigned by DashScope.

        Raises:
            RuntimeError: If task submission fails.
        """
        payload = {
            "model": "qwen3-asr-flash-filetrans",
            "input": {"file_url": file_url},
            "parameters": {
                "channel_id": channel_id,
                "language": language,
                "enable_itn": enable_itn,
            },
        }

        url = urljoin(self.base_url, "/api/v1/services/audio/asr/transcription")
        logger.info(f"Submitting transcription task for: {file_url}")

        response = self._make_request("POST", url, data=json.dumps(payload))
        if response.status_code == 200:
            task_id = response.json()["output"]["task_id"]
            logger.info(f"Transcription task submitted successfully. Task ID: {task_id}")
            return task_id
        else:
            error_detail = response.json()
            logger.error(f"Failed to submit task: {error_detail}")
            raise RuntimeError(f"Task submission failed: {error_detail}")


    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Retrieve the current status of a transcription task.

        Args:
            task_id: The task ID returned by `submit_transcription_task`.

        Returns:
            dict: Full task status response (see DashScope docs).
        """
        url = urljoin(self.base_url, f"/api/v1/tasks/{task_id}")
        response = self._make_request("GET", url)
        if response.status_code == 200:
            return response.json()
        else:
            error_detail = response.json()
            logger.error(f"Failed to fetch task status for {task_id}: {error_detail}")
            raise RuntimeError(f"Task status query failed: {error_detail}")


    def wait_for_completion(
        self,
        task_id: str,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Poll until the transcription task completes or timeout occurs.

        Args:
            task_id: The task ID to monitor.
            timeout: Maximum time (seconds) to wait. None means no timeout.

        Returns:
            dict: Final task result including `transcription_url`.

        Raises:
            TimeoutError: If timeout is reached before completion.
            RuntimeError: If task fails.
        """
        start_time = time.time()
        while True:
            status_response = self.get_task_status(task_id)
            task_status = status_response["output"]["task_status"]

            if task_status == "SUCCEEDED":
                logger.info(f"Task {task_id} completed successfully.")
                return status_response
            elif task_status == "FAILED":
                reason = status_response.get("output", {}).get("error_message", "Unknown error")
                logger.error(f"Task {task_id} failed: {reason}")
                logger.error(f"status_response={status_response}")
                raise RuntimeError(f"Transcription task failed: {reason}")
            else:
                logger.debug(f"Task {task_id} status: {task_status}")

            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Transcription task {task_id} did not complete within {timeout} seconds.")

            time.sleep(self.poll_interval)


    def fetch_transcript(self, transcription_url: str) -> Dict[str, Any]:
        """
        Download the final transcript from the result URL.

        Args:
            transcription_url: URL from the completed task's `result.transcription_url`.

        Returns:
            dict: Parsed JSON transcript containing sentence-level details.
        """
        logger.info(f"Fetching final transcript {transcription_url}")
        response = self._make_unauthenticated_request(transcription_url)
        response.raise_for_status()
        return response.json()
    

    def transcribe_audio(
        self,
        file_url: str,
        language: str = "en",
        channel_id: List[int] = [0],
        enable_itn: bool = False,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        High-level method to submit, wait for, and retrieve a full transcript.

        Args:
            file_url: Publicly accessible audio file URL.
            language: Language code.
            channel_id: Audio channels to transcribe.
            enable_itn: Enable inverse text normalization.
            timeout: Maximum time to wait for completion.

        Returns:
            dict: Final transcript JSON (with sentences, timestamps, etc.).
        """
        task_id = self.submit_transcription_task(file_url, language, channel_id, enable_itn)
        result = self.wait_for_completion(task_id, timeout=timeout)
        transcription_url = result["output"]["result"]["transcription_url"]
        return self.fetch_transcript(transcription_url)


# Example usage (uncomment for testing)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = DashScopeASRClient(region="beijing")
    transcript = client.transcribe_audio(
        file_url="https://your-audio-bucket.example.com/lecture.wav",
        language="en",
        timeout=600.0
    )
    print(json.dumps(transcript, indent=2))