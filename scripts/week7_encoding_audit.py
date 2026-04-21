from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

TEXT_SUFFIXES = {
    ".bat",
    ".cmd",
    ".conf",
    ".css",
    ".csv",
    ".env",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".ps1",
    ".py",
    ".scss",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}

TEXT_FILENAMES = {
    ".hintrc",
    ".vercelignore",
    "LICENSE",
    "README",
    "README.md",
    "TODO",
}

SKIP_DIR_NAMES = {
    ".git",
    ".tmp",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "output",
    "venv",
}

SKIP_DIR_PREFIXES = ("pytest-cache-files-",)

MOJIBAKE_CJK_MARKERS = ("\u951f", "\u951b", "\u9286")
LATIN_MOJIBAKE_LEADS = {0x00C2, 0x00C3, 0x00D0, 0x00D1, 0x00F0}


@dataclass(slots=True)
class Issue:
    path: str
    issue_type: str
    detail: str
    line: int | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "path": self.path,
            "type": self.issue_type,
            "detail": self.detail,
        }
        if self.line is not None:
            payload["line"] = self.line
        return payload


def _should_skip(path: Path) -> bool:
    for part in path.parts:
        if part in SKIP_DIR_NAMES:
            return True
        if any(part.startswith(prefix) for prefix in SKIP_DIR_PREFIXES):
            return True
    return False


def _is_text_candidate(path: Path) -> bool:
    name = path.name
    suffix = path.suffix.lower()
    return suffix in TEXT_SUFFIXES or name in TEXT_FILENAMES


def _iter_candidates(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if _should_skip(rel):
            continue
        if not _is_text_candidate(rel):
            continue
        yield path


def _line_of_index(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _find_latin_mojibake(text: str) -> tuple[int, str] | None:
    if len(text) < 2:
        return None

    for idx in range(len(text) - 1):
        first = ord(text[idx])
        second = ord(text[idx + 1])
        if first not in LATIN_MOJIBAKE_LEADS:
            continue

        # Common UTF-8-as-Latin1 mojibake signatures such as "\u00c3x", "\u00c2x", or "\u00d0x".
        if 0x0080 <= second <= 0x024F:
            return idx, text[idx : idx + 2]
    return None


def _console_safe(value: str) -> str:
    return value.encode("ascii", "backslashreplace").decode("ascii")


def scan_repo(root: Path) -> tuple[list[Issue], int]:
    issues: list[Issue] = []
    scanned_files = 0

    for path in _iter_candidates(root):
        scanned_files += 1
        rel = path.relative_to(root).as_posix()
        raw = path.read_bytes()

        # Best-effort binary skip for misclassified assets.
        if b"\x00" in raw:
            continue

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            issues.append(
                Issue(
                    path=rel,
                    issue_type="non_utf8",
                    detail=f"Invalid UTF-8 sequence at byte {exc.start}: {exc.reason}",
                )
            )
            continue

        replacement_count = text.count("\ufffd")
        if replacement_count:
            issues.append(
                Issue(
                    path=rel,
                    issue_type="replacement_char",
                    detail=f"Found U+FFFD replacement char {replacement_count} time(s).",
                )
            )

        latin_mojibake = _find_latin_mojibake(text)
        if latin_mojibake is not None:
            idx, hit = latin_mojibake
            issues.append(
                Issue(
                    path=rel,
                    issue_type="mojibake_pattern",
                    detail=f"Matched suspicious sequence `{hit}`.",
                    line=_line_of_index(text, idx),
                )
            )

        cjk_marker_hits = sum(text.count(marker) for marker in MOJIBAKE_CJK_MARKERS)
        if cjk_marker_hits >= 3:
            issues.append(
                Issue(
                    path=rel,
                    issue_type="mojibake_cjk_markers",
                    detail=f"Found {cjk_marker_hits} suspicious CJK marker characters.",
                )
            )

    return issues, scanned_files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Week7 encoding audit: UTF-8 validation and mojibake checks."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to scan.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/week7/encoding-audit-report.json"),
        help="Where to write the JSON report.",
    )
    parser.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="Exit with code 1 if any issue is detected.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    issues, scanned_files = scan_repo(root)
    issue_counter = Counter(item.issue_type for item in issues)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": root.as_posix(),
        "summary": {
            "scanned_files": scanned_files,
            "issue_count": len(issues),
            "issue_types": dict(sorted(issue_counter.items())),
        },
        "issues": [item.to_dict() for item in issues],
    }

    output_path = args.output
    if not output_path.is_absolute():
        output_path = root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Encoding audit scanned {scanned_files} file(s).")
    print(f"Issues found: {len(issues)}")
    print(f"Report: {output_path.as_posix()}")
    if issues:
        for issue in issues[:20]:
            suffix = f":{issue.line}" if issue.line is not None else ""
            detail = _console_safe(issue.detail)
            print(f"- {issue.path}{suffix} [{issue.issue_type}] {detail}")
        if len(issues) > 20:
            print(f"... {len(issues) - 20} more issue(s) omitted from console output.")

    if args.fail_on_issues and issues:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
