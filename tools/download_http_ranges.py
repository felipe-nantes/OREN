#!/usr/bin/env python3
"""Download a large HTTP file with verified resumable byte ranges."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import threading
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def split_ranges(total_bytes: int, workers: int) -> list[tuple[int, int]]:
    if total_bytes <= 0 or workers <= 0:
        raise ValueError("total_bytes and workers must be positive")
    width = (total_bytes + workers - 1) // workers
    return [
        (start, min(total_bytes - 1, start + width - 1))
        for start in range(0, total_bytes, width)
    ]


def _download_part(
    *, url: str, path: Path, start: int, end: int, timeout: float,
) -> dict[str, int | str]:
    expected = end - start + 1
    existing = path.stat().st_size if path.exists() else 0
    if existing > expected:
        raise RuntimeError(f"Part larger than expected: {path}")
    if existing == expected:
        return {"path": str(path), "bytes": existing, "status": "reused"}
    request_start = start + existing
    request = urllib.request.Request(
        url,
        headers={
            "Range": f"bytes={request_start}-{end}",
            "User-Agent": "ARGOS-research-benchmark/1.0",
            "Accept-Encoding": "identity",
            "Connection": "close",
        },
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        if response.status != 206:
            raise RuntimeError(f"Server ignored Range for {path}: HTTP {response.status}")
        content_range = response.headers.get("Content-Range", "")
        expected_prefix = f"bytes {request_start}-{end}/"
        if not content_range.startswith(expected_prefix):
            raise RuntimeError(f"Unexpected Content-Range for {path}: {content_range!r}")
        with path.open("ab") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    actual = path.stat().st_size
    if actual != expected:
        raise RuntimeError(f"Incomplete part {path}: {actual} != {expected}")
    return {"path": str(path), "bytes": actual, "status": "downloaded"}


def download_ranged(
    *,
    url: str,
    output: Path,
    total_bytes: int,
    expected_md5: str,
    workers: int = 4,
    timeout: float = 120.0,
) -> dict[str, object]:
    output = Path(output).resolve()
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite existing output: {output}")
    ranges = split_ranges(total_bytes, workers)
    parts_dir = output.with_name(f".{output.name}.range-parts")
    parts_dir.mkdir(parents=True, exist_ok=True)
    part_specs = [
        (parts_dir / f"part-{index:03d}.bin", start, end)
        for index, (start, end) in enumerate(ranges)
    ]
    lock = threading.Lock()
    started = time.monotonic()
    completed: list[dict[str, int | str]] = []
    with ThreadPoolExecutor(max_workers=len(part_specs)) as executor:
        futures = {
            executor.submit(
                _download_part,
                url=url,
                path=path,
                start=start,
                end=end,
                timeout=timeout,
            ): path
            for path, start, end in part_specs
        }
        last_report = 0.0
        while futures:
            finished = [future for future in futures if future.done()]
            for future in finished:
                path = futures.pop(future)
                result = future.result()
                with lock:
                    completed.append(result)
                print(json.dumps({"event": "part_complete", **result}), flush=True)
            now = time.monotonic()
            if now - last_report >= 20.0 and futures:
                downloaded = sum(path.stat().st_size for path, _, _ in part_specs if path.exists())
                print(
                    json.dumps(
                        {
                            "event": "progress",
                            "bytes": downloaded,
                            "total_bytes": total_bytes,
                            "percent": round(100.0 * downloaded / total_bytes, 3),
                            "elapsed_seconds": round(now - started, 1),
                        }
                    ),
                    flush=True,
                )
                last_report = now
            if futures:
                time.sleep(1.0)

    temporary = output.with_name(f".{output.name}.assembling.{uuid.uuid4().hex}")
    digest = hashlib.md5(usedforsecurity=False)
    try:
        with temporary.open("wb") as destination:
            for path, start, end in part_specs:
                if path.stat().st_size != end - start + 1:
                    raise RuntimeError(f"Part size changed before assembly: {path}")
                with path.open("rb") as source:
                    while chunk := source.read(8 * 1024 * 1024):
                        destination.write(chunk)
                        digest.update(chunk)
        if temporary.stat().st_size != total_bytes:
            raise RuntimeError("Assembled file has unexpected size")
        actual_md5 = digest.hexdigest()
        if actual_md5.lower() != expected_md5.lower():
            raise RuntimeError(f"MD5 mismatch: {actual_md5} != {expected_md5}")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    shutil.rmtree(parts_dir)
    return {
        "output": str(output),
        "bytes": total_bytes,
        "md5": expected_md5.lower(),
        "workers": len(part_specs),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "status": "verified_and_published",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bytes", type=int, required=True)
    parser.add_argument("--md5", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args(argv)
    result = download_ranged(
        url=args.url,
        output=args.out,
        total_bytes=args.bytes,
        expected_md5=args.md5,
        workers=args.workers,
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
