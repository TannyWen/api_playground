"""Single source of truth for what's actually running.

Exists separately from app.main (rather than reading app.main.app.version)
purely to avoid a circular import: app.main imports the /v1 router, and /v1
routes need this too. Bump __version__ whenever a change is worth being able
to see from the outside.
"""
import pathlib
from datetime import datetime, timezone

__version__ = "2.1.0"

# The moment THIS PROCESS started, not when the code was written. This is
# the one field that answers "did a restart / redeploy actually happen" even
# if __version__ was left unbumped by mistake -- it changes every time a new
# process boots and stays fixed for as long as that process keeps running.
STARTED_AT = datetime.now(timezone.utc)


def git_commit() -> str | None:
    """Best-effort short commit SHA, read directly from .git.

    No `git` binary required -- the deployed container may not have one.
    Returns None if .git isn't part of the deployed artifact, which depends
    on the deploy mechanism and isn't guaranteed.
    """
    try:
        root = pathlib.Path(__file__).resolve().parent.parent
        git_dir = root / ".git"
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref_path = git_dir / head.split(" ", 1)[1].strip()
            sha = ref_path.read_text(encoding="utf-8").strip()
        else:
            sha = head
        return sha[:8]
    except OSError:
        return None
