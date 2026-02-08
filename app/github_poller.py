"""
Polls GitHub API for new commits and pulls to local directory.
"""
import logging
import re
import threading
import time
from typing import Callable

import requests

from . import git_ops

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _normalize_repo(repo: str) -> str:
    """Convert 'https://github.com/owner/repo.git' -> 'owner/repo'."""
    repo = repo.strip()
    m = re.match(r"https?://github\.com/([^/]+)/([^/.]+)", repo)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    if repo.startswith("git@"):
        m = re.search(r"github\.com:([^/]+)/([^.]+)", repo)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return repo


def fetch_latest_sha(owner: str, repo_name: str, branch: str, token: str | None) -> str | None:
    """Fetch latest commit SHA for branch from GitHub API. Returns None on failure."""
    url = f"{GITHUB_API}/repos/{owner}/{repo_name}/commits/{branch}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("sha")
    except requests.RequestException as e:
        logger.warning("Failed to fetch commit SHA for %s/%s: %s", owner, repo_name, e)
        return None


def poll_loop(
    repo: str,
    local_path: str,
    token: str | None,
    branch: str,
    interval_seconds: int,
    stop_event: threading.Event,
    on_pull: Callable[[], None] | None = None,
) -> None:
    """Run polling loop: check GitHub for new commit, clone or pull as needed."""
    normalized = _normalize_repo(repo)
    if "/" not in normalized:
        logger.error("Invalid repo format: %s", repo)
        return
    owner, repo_name = normalized.split("/", 1)
    last_sha: str | None = None

    while not stop_event.is_set():
        try:
            sha = fetch_latest_sha(owner, repo_name, branch, token)
            if sha is None:
                time.sleep(interval_seconds)
                continue

            if not git_ops.is_git_repo(local_path):
                logger.info("Cloning %s into %s", repo, local_path)
                if git_ops.clone(repo, local_path, token, branch):
                    last_sha = sha
                    if on_pull:
                        on_pull()
                else:
                    logger.error("Clone failed for %s", repo)
            elif last_sha is not None and sha != last_sha:
                logger.info("New commit on %s, pulling", repo)
                if git_ops.pull(local_path, token, repo):
                    last_sha = sha
                    if on_pull:
                        on_pull()
            else:
                if last_sha is None:
                    last_sha = sha
        except Exception as e:
            logger.exception("Poll error for %s: %s", repo, e)

        stop_event.wait(interval_seconds)
