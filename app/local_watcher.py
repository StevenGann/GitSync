"""
Watches local directories for file changes; debounces and commits + pushes.
"""
import logging
import threading
import time
from pathlib import Path

import watchdog.events
import watchdog.observers

from . import git_ops

logger = logging.getLogger(__name__)


class DebouncedCommitHandler(watchdog.events.FileSystemEventHandler):
    """On file event, reset debounce timer; when timer fires, commit and push."""

    def __init__(
        self,
        local_path: str,
        debounce_seconds: int,
        user_name: str,
        user_email: str,
        token: str | None,
        repo: str | None,
        branch: str | None,
        pull_before_push: bool,
    ):
        super().__init__()
        self.local_path = local_path
        self.debounce_seconds = debounce_seconds
        self.user_name = user_name
        self.user_email = user_email
        self.token = token
        self.repo = repo
        self.branch = branch
        self.pull_before_push = pull_before_push
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def _reset_timer(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_seconds, self._on_timer)
            self._timer.daemon = True
            self._timer.start()

    def _on_timer(self) -> None:
        with self._lock:
            self._timer = None
        self._do_commit_and_push(self.local_path)

    def _do_commit_and_push(self, local_path: str) -> None:
        if not git_ops.is_git_repo(local_path):
            return
        if not git_ops.has_changes(local_path):
            return
        logger.info("Committing and pushing changes in %s", local_path)
        if self.pull_before_push:
            if not git_ops.pull_before_push(local_path, self.repo, self.token):
                logger.warning("Pull before push failed, skipping push")
                return
        if not git_ops.add_all(local_path):
            return
        if not git_ops.commit(
            local_path,
            "GitSync: auto sync",
            self.user_name,
            self.user_email,
        ):
            return
        if not git_ops.push(local_path, self.token, self.branch, self.repo):
            logger.error("Push failed for %s", local_path)

    def _on_event(self, event: watchdog.events.FileSystemEvent) -> None:
        # Ignore .git directory changes
        src = str(event.src_path) if event.src_path else ""
        if ".git" in Path(src).parts:
            return
        self._reset_timer()

    def on_modified(self, event: watchdog.events.FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._on_event(event)

    def on_created(self, event: watchdog.events.FileSystemEvent) -> None:
        self._on_event(event)

    def on_deleted(self, event: watchdog.events.FileSystemEvent) -> None:
        self._on_event(event)

    def on_moved(self, event: watchdog.events.FileSystemMovedEvent) -> None:
        self._on_event(event)


def watch_loop(
    local_path: str,
    debounce_seconds: int,
    user_name: str,
    user_email: str,
    token: str | None,
    repo: str | None,
    branch: str | None,
    pull_before_push: bool,
    stop_event: threading.Event,
) -> None:
    """Start watchdog observer on local_path with debounced commit+push."""
    path = Path(local_path)
    while not path.exists() and not stop_event.is_set():
        stop_event.wait(5)
    if not path.exists():
        return
    handler = DebouncedCommitHandler(
        local_path=str(path),
        debounce_seconds=debounce_seconds,
        user_name=user_name,
        user_email=user_email,
        token=token,
        repo=repo,
        branch=branch,
        pull_before_push=pull_before_push,
    )
    observer = watchdog.observers.Observer()
    observer.schedule(handler, str(path), recursive=True)
    observer.start()
    logger.info("Watching %s (debounce=%ds)", local_path, debounce_seconds)
    try:
        while not stop_event.is_set():
            stop_event.wait(1.0)
    finally:
        observer.stop()
        observer.join(timeout=5.0)
