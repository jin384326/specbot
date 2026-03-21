from __future__ import annotations

import concurrent.futures
import json
import time
import zipfile
from io import BytesIO
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib import error, parse, request


RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


@dataclass
class VespaEndpoint:
    base_url: str
    schema: str = "spec_finder"
    namespace: str = "spec_finder"
    config_base_url: str | None = None

    @property
    def document_endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/document/v1/{self.namespace}/{self.schema}/docid"

    @property
    def query_endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/search/"

    @property
    def config_endpoint(self) -> str:
        base = (self.config_base_url or self.base_url).rstrip("/")
        return f"{base}/application/v2/tenant/default"


@dataclass
class VespaFeedAttempt:
    doc_id: str
    success: bool
    status_code: int | None = None
    response: dict[str, Any] | None = None
    error: str = ""
    attempts: int = 0


@dataclass
class VespaFeedSummary:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    attempts: list[VespaFeedAttempt] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "attempts": [
                {
                    "doc_id": item.doc_id,
                    "success": item.success,
                    "status_code": item.status_code,
                    "error": item.error,
                    "attempts": item.attempts,
                    "response": item.response,
                }
                for item in self.attempts
            ],
        }


def _read_http_error(exc: error.HTTPError) -> str:
    return exc.read().decode("utf-8", errors="replace")


def _http_json(
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | bytes | None = None,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = None
    if payload is not None:
        if isinstance(payload, bytes):
            data = payload
        else:
            data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    req = request.Request(url=url, data=data, headers=request_headers, method=method)
    with request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def _request_with_retry(
    url: str,
    method: str,
    payload: dict[str, Any] | bytes | None,
    timeout: float,
    max_retries: int,
    retry_backoff_seconds: float,
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, int | None, str, int]:
    attempts = 0
    while True:
        attempts += 1
        try:
            response = _http_json(url=url, method=method, payload=payload, timeout=timeout, headers=headers)
            return response, 200, "", attempts
        except error.HTTPError as exc:
            status_code = exc.code
            detail = _read_http_error(exc)
            if status_code in RETRYABLE_STATUS_CODES and attempts <= max_retries:
                time.sleep(retry_backoff_seconds * attempts)
                continue
            return None, status_code, detail, attempts
        except error.URLError as exc:
            if attempts <= max_retries:
                time.sleep(retry_backoff_seconds * attempts)
                continue
            return None, None, str(exc.reason), attempts


def iter_jsonl_documents(jsonl_path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(jsonl_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def chunked(iterable: Iterable[dict[str, Any]], batch_size: int) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def feed_document(
    endpoint: VespaEndpoint,
    document: dict[str, Any],
    timeout: float = 30.0,
    max_retries: int = 2,
    retry_backoff_seconds: float = 0.5,
) -> VespaFeedAttempt:
    put_value = document["put"]
    doc_id = put_value.rsplit("::", 1)[-1]
    url = f"{endpoint.document_endpoint}/{parse.quote(doc_id, safe='')}"
    response, status_code, error_message, attempts = _request_with_retry(
        url=url,
        method="POST",
        payload={"fields": document["fields"]},
        timeout=timeout,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
    )
    if error_message:
        return VespaFeedAttempt(
            doc_id=doc_id,
            success=False,
            status_code=status_code,
            error=error_message,
            attempts=attempts,
        )
    return VespaFeedAttempt(
        doc_id=doc_id,
        success=True,
        status_code=status_code,
        response=response,
        attempts=attempts,
    )


def feed_documents(
    endpoint: VespaEndpoint,
    feed_documents: Iterable[dict[str, Any]],
    timeout: float = 30.0,
    max_retries: int = 2,
    retry_backoff_seconds: float = 0.5,
    max_workers: int = 1,
) -> VespaFeedSummary:
    summary = VespaFeedSummary()
    documents = list(feed_documents)
    worker_count = max(1, min(max_workers, len(documents) or 1))
    attempts: Iterable[VespaFeedAttempt]
    if worker_count == 1:
        attempts = (
            feed_document(
                endpoint,
                document,
                timeout=timeout,
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff_seconds,
            )
            for document in documents
        )
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            attempts = executor.map(
                lambda document: feed_document(
                    endpoint,
                    document,
                    timeout=timeout,
                    max_retries=max_retries,
                    retry_backoff_seconds=retry_backoff_seconds,
                ),
                documents,
            )
    for attempt in attempts:
        summary.total += 1
        if attempt.success:
            summary.succeeded += 1
        else:
            summary.failed += 1
        summary.attempts.append(attempt)
    return summary


def feed_jsonl_file(
    endpoint: VespaEndpoint,
    jsonl_path: str | Path,
    timeout: float = 30.0,
    max_retries: int = 2,
    retry_backoff_seconds: float = 0.5,
    batch_size: int = 100,
    max_workers: int = 1,
) -> dict[str, Any]:
    aggregate = VespaFeedSummary()
    for batch in chunked(iter_jsonl_documents(jsonl_path), batch_size=batch_size):
        summary = feed_documents(
            endpoint,
            batch,
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            max_workers=max_workers,
        )
        aggregate.total += summary.total
        aggregate.succeeded += summary.succeeded
        aggregate.failed += summary.failed
        aggregate.attempts.extend(summary.attempts)
    return aggregate.to_dict()


def query_vespa(
    endpoint: VespaEndpoint,
    query_params: dict[str, Any],
    timeout: float = 30.0,
    max_retries: int = 1,
    retry_backoff_seconds: float = 0.5,
) -> dict[str, Any]:
    encoded = parse.urlencode({key: value for key, value in query_params.items() if value is not None})
    url = f"{endpoint.query_endpoint}?{encoded}"
    response, status_code, error_message, attempts = _request_with_retry(
        url=url,
        method="GET",
        payload=None,
        timeout=timeout,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
    )
    if error_message:
        raise RuntimeError(
            f"Vespa query failed for {url} after {attempts} attempts"
            + (f" with HTTP {status_code}" if status_code else "")
            + f": {error_message}"
        )
    return response or {}


def build_application_package_bytes(app_dir: str | Path) -> bytes:
    root = Path(app_dir)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(root))
    return buffer.getvalue()


def deploy_application_package(
    endpoint: VespaEndpoint,
    app_dir: str | Path,
    timeout: float = 60.0,
    max_retries: int = 1,
    retry_backoff_seconds: float = 1.0,
) -> dict[str, Any]:
    payload = build_application_package_bytes(app_dir)
    url = f"{endpoint.config_endpoint}/prepareandactivate"
    response, status_code, error_message, attempts = _request_with_retry(
        url=url,
        method="POST",
        payload=payload,
        timeout=timeout,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        headers={"Content-Type": "application/zip"},
    )
    if error_message:
        raise RuntimeError(
            f"Vespa deploy failed for {url} after {attempts} attempts"
            + (f" with HTTP {status_code}" if status_code else "")
            + f": {error_message}"
        )
    return response or {}


def smoke_test_vespa(
    endpoint: VespaEndpoint,
    query_params: dict[str, Any],
    timeout: float = 30.0,
) -> dict[str, Any]:
    response = query_vespa(endpoint, query_params, timeout=timeout)
    root = response.get("root", {})
    children = root.get("children", [])
    return {
        "total_hit_count": root.get("fields", {}).get("totalCount", 0),
        "returned_hits": len(children),
        "top_ids": [child.get("id", "") for child in children[:5]],
        "raw": response,
    }


def wait_for_vespa(
    endpoint: VespaEndpoint,
    timeout_seconds: float = 60.0,
    poll_interval_seconds: float = 2.0,
    require_config: bool = False,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error = "unknown"
    attempts = 0
    while time.time() < deadline:
        attempts += 1
        try:
            query_vespa(endpoint, {"yql": "select * from sources * where true", "hits": 0}, timeout=poll_interval_seconds)
            if require_config:
                _http_json(
                    url=endpoint.config_endpoint,
                    method="GET",
                    timeout=poll_interval_seconds,
                )
            return {"ready": True, "attempts": attempts}
        except Exception as exc:  # pragma: no cover - concrete cases tested via mocks
            last_error = str(exc)
            time.sleep(poll_interval_seconds)
    return {"ready": False, "attempts": attempts, "error": last_error}
