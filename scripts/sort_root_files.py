"""Sort files in the project root into folders by type.

Safety first:
- Default mode is DRY-RUN (no changes).
- Actual moves happen only with --apply.
- Protects common project entrypoints/configs from being moved.

Typical usage:
  python scripts/sort_root_files.py
  python scripts/sort_root_files.py --apply

Optional:
  python scripts/sort_root_files.py --apply --include-readme-todo

Notes:
- This script is intentionally conservative. Edit KEEP_FILES / rules below if needed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class MoveAction:
    src: Path
    dst: Path


# Files that are commonly expected to live in the repo root.
# This list is conservative on purpose.
KEEP_FILES = {
    # Python modules in root
    # (root entrypoints removed; runtime code is under app/entrypoints)
    # Core files
    "requirements.txt",
    # Environment
    ".env",
    # SSH keys (do not move automatically)
    "github_ssh_private_ed25519",
    "github_ssh_public_ed25519.pub",
}

# Docs that are often expected in root (GitHub, IDE, etc.).
ROOT_DOCS = {
    "README.md",
    "TODO.md",
}


DOC_EXTS = {".md", ".txt", ".rst"}
DATA_EXTS = {".json", ".jsonl", ".csv"}
WEB_EXTS = {".html", ".js", ".css"}
ARCHIVE_EXTS = {".zip", ".tar", ".gz"}


def project_root_from_here() -> Path:
    # scripts/sort_root_files.py -> project root is one level up
    return Path(__file__).resolve().parents[1]


def is_archive(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(".tar.gz"):
        return True
    return path.suffix.lower() in ARCHIVE_EXTS


def classify(root: Path, file_path: Path, *, include_root_docs: bool) -> Path | None:
    """Return target directory (absolute path) or None to keep file in place."""

    name = file_path.name

    if name in KEEP_FILES:
        return None

    if (not include_root_docs) and (name in ROOT_DOCS):
        return None

    # Keep typical IDE/venv/git metadata untouched.
    if name.startswith("."):
        return None

    # Temporary files in root -> existing tmp/
    if name.startswith("tmp_"):
        return root / "tmp"

    if is_archive(file_path):
        return root / "artifacts" / "archives"

    ext = file_path.suffix.lower()

    if ext in DOC_EXTS:
        return root / "docs"

    if ext in DATA_EXTS:
        # Prefer existing data/ folder, keep exports separate.
        return root / "data" / "exports"

    if ext in WEB_EXTS:
        return root / "artifacts" / "web"

    return None


def iter_root_files(root: Path) -> Iterable[Path]:
    for p in root.iterdir():
        if p.is_file():
            yield p


def plan_moves(root: Path, *, include_root_docs: bool) -> list[MoveAction]:
    actions: list[MoveAction] = []

    for src in iter_root_files(root):
        target_dir = classify(root, src, include_root_docs=include_root_docs)
        if target_dir is None:
            continue

        dst = target_dir / src.name
        if dst == src:
            continue

        actions.append(MoveAction(src=src, dst=dst))

    # Stable output for readability
    actions.sort(key=lambda a: (str(a.dst.parent).lower(), a.src.name.lower()))
    return actions


def ensure_parent_dirs(actions: list[MoveAction], *, apply: bool) -> None:
    if not apply:
        return

    for action in actions:
        action.dst.parent.mkdir(parents=True, exist_ok=True)


def execute_moves(actions: list[MoveAction], *, apply: bool) -> None:
    for action in actions:
        if action.dst.exists():
            print(f"SKIP (exists): {action.src.name} -> {action.dst}")
            continue

        if not apply:
            print(f"DRY: {action.src.name} -> {action.dst}")
            continue

        action.src.replace(action.dst)
        print(f"MOVED: {action.src.name} -> {action.dst}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sort project root files into folders by type.")
    parser.add_argument(
        "--root",
        type=Path,
        default=project_root_from_here(),
        help="Project root folder (default: inferred from script location)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move files (default: dry-run)",
    )
    parser.add_argument(
        "--include-readme-todo",
        action="store_true",
        help="Also move README.md / TODO.md into docs/",
    )

    args = parser.parse_args()
    root: Path = args.root.resolve()

    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Root path does not exist or is not a directory: {root}")

    actions = plan_moves(root, include_root_docs=args.include_readme_todo)

    print(f"Root: {root}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"Planned moves: {len(actions)}")

    if not actions:
        return 0

    ensure_parent_dirs(actions, apply=args.apply)
    execute_moves(actions, apply=args.apply)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
