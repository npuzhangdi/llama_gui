# -*- coding: utf-8 -*-
"""Pick the fastest PyPI mirror for this computer.

Standard library only, so it can run inside a brand-new venv before any
third-party package is installed. Progress goes to stderr, the winning URL
goes to stdout, and the full ranking is written to --out (one URL per line)
so the batch installer can fall back to the next mirror if pip fails.

All console output is ASCII: cmd.exe may be using any OEM code page.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import ssl
import sys
import time
import urllib.request

MIRRORS: list[tuple[str, str]] = [
    ("PyPI", "https://pypi.org/simple"),
    ("Tsinghua", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("Aliyun", "https://mirrors.aliyun.com/pypi/simple"),
    ("USTC", "https://mirrors.ustc.edu.cn/pypi/simple"),
    ("Tencent", "https://mirrors.cloud.tencent.com/pypi/simple"),
    ("Huawei", "https://repo.huaweicloud.com/repository/pypi/simple"),
    ("Douban", "https://pypi.doubanio.com/simple"),
]

DEFAULT_INDEX = MIRRORS[0][1]
PROBE_PATH = "/pip/"          # small page that exists on every PEP-503 index
READ_LIMIT = 64 * 1024       # only the first bytes matter for a latency probe


def probe(entry: tuple[str, str], timeout: float):
    """Return (name, url, elapsed_ms_or_inf, bytes_read, error_text)."""
    name, base = entry
    url = base.rstrip("/") + PROBE_PATH
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "LlamaStudio-MirrorProbe/1.0",
            "Accept": "*/*",
            "Cache-Control": "no-cache",
        },
    )
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise OSError("HTTP %s" % status)
            data = response.read(READ_LIMIT)
        elapsed = (time.perf_counter() - started) * 1000.0
        return name, base, elapsed, len(data), ""
    except Exception as exc:  # noqa: BLE001 - any failure just ranks this mirror last
        detail = str(exc).encode("ascii", "replace").decode("ascii")[:70]
        return name, base, float("inf"), 0, "%s: %s" % (type(exc).__name__, detail)


def default_order() -> list[str]:
    return [url for _name, url in MIRRORS]


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark PyPI mirrors.")
    parser.add_argument("--out", default="", help="write the ranked URL list here")
    parser.add_argument("--best", default="", help="write only the winning URL here")
    parser.add_argument("--timeout", type=float, default=4.0,
                        help="per-mirror timeout in seconds (default 4)")
    args = parser.parse_args()

    print("  Probing %d package indexes (timeout %.1fs each, in parallel) ..."
          % (len(MIRRORS), args.timeout), file=sys.stderr)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(MIRRORS)) as pool:
            results = list(pool.map(lambda item: probe(item, args.timeout), MIRRORS))
    except Exception as exc:  # noqa: BLE001 - never block the installer
        print("  Probe failed (%s); using the default order." % type(exc).__name__,
              file=sys.stderr)
        results = [(name, url, float("inf"), 0, "skipped") for name, url in MIRRORS]

    ranked = sorted(results, key=lambda row: (row[2], MIRRORS.index((row[0], row[1]))))
    for name, _url, elapsed, size, error in ranked:
        if error:
            print("  %-10s unreachable  %s" % (name, error), file=sys.stderr)
        else:
            print("  %-10s %7.0f ms  (%d bytes)" % (name, elapsed, size), file=sys.stderr)

    usable = [row[1] for row in ranked if row[2] != float("inf")]
    unreachable = [row[1] for row in ranked if row[2] == float("inf")]
    order = usable + unreachable
    if not order:
        order = default_order()

    if args.out:
        try:
            with open(args.out, "w", encoding="ascii", newline="\r\n") as handle:
                for url in order:
                    handle.write(url + "\n")
        except OSError as exc:
            print("  Could not write %s (%s)" % (args.out, exc), file=sys.stderr)
    if args.best:
        try:
            with open(args.best, "w", encoding="ascii", newline="\r\n") as handle:
                handle.write(order[0] + "\n")
        except OSError as exc:
            print("  Could not write %s (%s)" % (args.best, exc), file=sys.stderr)

    print(order[0])  # stdout must contain exactly one line: the chosen URL
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
