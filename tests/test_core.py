from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from context_pack import (
    ContextPackError,
    build_context_pack,
    estimate_tokens,
    render_json,
    render_markdown,
)


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_repo"


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "initial")
    return repo


def test_explicit_selection_is_sorted_and_explains_filters(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    pack = build_context_pack(
        repo,
        files=["src/unique.py", "ignored.txt", "src/beta.py", "src/alpha.py", "missing.py"],
    )

    assert [item.path for item in pack.files] == ["src/alpha.py", "src/unique.py"]
    assert [item.path for item in pack.exclusions] == [
        "ignored.txt",
        "missing.py",
        "src/beta.py",
    ]
    assert {item.reason for item in pack.exclusions} == {"ignored", "missing", "duplicate"}
    assert pack.total_bytes == sum(item.byte_count for item in pack.files)
    assert pack.total_tokens == sum(item.token_count for item in pack.files)


def test_ignored_file_can_be_explicitly_allowed(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    excluded = build_context_pack(repo, files=["ignored.txt"])
    included = build_context_pack(repo, files=["ignored.txt"], include_ignored=True)

    assert not excluded.files
    assert excluded.exclusions[0].reason == "ignored"
    assert [item.path for item in included.files] == ["ignored.txt"]


def test_duplicate_and_budgets_are_deterministic(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    alpha = (repo / "src/alpha.py").read_bytes()

    duplicate = build_context_pack(repo, files=["src/alpha.py", "src/beta.py"])
    assert [item.path for item in duplicate.files] == ["src/alpha.py"]
    assert duplicate.exclusions[0].reason == "duplicate"

    budget = build_context_pack(
        repo,
        files=["src/alpha.py", "src/unique.py"],
        max_bytes=len(alpha),
        max_tokens=estimate_tokens(alpha),
    )
    assert [item.path for item in budget.files] == ["src/alpha.py"]
    assert {item.reason for item in budget.exclusions} == {"byte-budget"}


def test_changed_selection_includes_tracked_changes_and_new_files(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    (repo / "new.py").write_text("print('new')\n", encoding="utf-8")
    (repo / "ignored.txt").write_text("still ignored\n", encoding="utf-8")

    pack = build_context_pack(repo, changed=True)

    assert pack.selection == "changed"
    assert [item.path for item in pack.files] == ["README.md", "new.py"]
    assert all(item.path != "ignored.txt" for item in pack.files)


def test_changed_selection_can_include_ignored_files(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "ignored.txt").write_text("now changed\n", encoding="utf-8")

    pack = build_context_pack(repo, changed=True, include_ignored=True)

    assert [item.path for item in pack.files] == ["build/generated.py", "ignored.txt"]


def test_changed_selection_works_before_the_first_commit(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "first.py").write_text("print('first')\n", encoding="utf-8")

    pack = build_context_pack(repo, changed=True)

    assert [item.path for item in pack.files] == ["first.py"]


def test_binary_and_outside_paths_are_explained(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "data.bin").write_bytes(b"prefix\0suffix")
    outside = tmp_path / "outside.txt"
    outside.write_text("do not read\n", encoding="utf-8")

    pack = build_context_pack(repo, files=["data.bin", str(outside)])

    assert not pack.files
    reasons = {(item.path, item.reason) for item in pack.exclusions}
    assert ("data.bin", "binary") in reasons
    assert (str(outside), "outside-repository") in reasons


def test_json_and_markdown_rendering_are_stable(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    pack = build_context_pack(repo, files=["src/quote.md"])

    payload = json.loads(render_json(pack))
    assert payload["files"][0]["path"] == "src/quote.md"
    assert "## Exclusions" in render_markdown(pack)
    markdown = render_markdown(pack)
    assert "`````markdown" in markdown
    assert "not Markdown syntax in the source" in markdown
    assert render_json(pack) == render_json(pack)


def test_invalid_arguments_fail_closed(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    with pytest.raises(ContextPackError, match="budgets"):
        build_context_pack(repo, files=["README.md"], max_bytes=-1)
    with pytest.raises(ContextPackError, match="changed or explicit"):
        build_context_pack(repo, files=["README.md"], changed=True)
    with pytest.raises(ContextPackError, match="base"):
        build_context_pack(repo, files=["README.md"], base="HEAD")
