"""
GitSync: Monitors GitHub for new commits (pulls) and local dirs for changes (debounced commit+push).
"""
import json
import logging
import os
import signal
import sys
import threading
from pathlib import Path

from . import github_poller
from . import local_watcher

logger = logging.getLogger(__name__)


def load_config(path: str) -> dict:
    """Load and validate config.json."""
    p = Path(path)
    if not p.exists():
        logger.error("Config file not found: %s", path)
        sys.exit(1)
    try:
        with open(p, encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in config: %s", e)
        sys.exit(1)
    if "repos" not in cfg or not cfg["repos"]:
        logger.error("Config must have non-empty 'repos' array")
        sys.exit(1)
    return cfg


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    config_path = os.environ.get("CONFIG_PATH", "/config/config.json")
    token = os.environ.get("GITHUB_TOKEN")  # Override config if set
    cfg = load_config(config_path)
    if token:
        cfg["github_token"] = token
    poll_interval = int(cfg.get("poll_interval_seconds", 60))
    debounce = int(cfg.get("debounce_seconds", 30))
    user_name = cfg.get("git_user_name", "GitSync")
    user_email = cfg.get("git_user_email", "gitsync@local")
    pull_before_push = cfg.get("pull_before_push", True)

    stop = threading.Event()

    def on_stop(signum=None, frame=None):
        stop.set()

    signal.signal(signal.SIGTERM, on_stop)
    signal.signal(signal.SIGINT, on_stop)

    threads: list[threading.Thread] = []
    for r in cfg["repos"]:
        repo = r.get("repo")
        local_path = r.get("local_path")
        if not repo or not local_path:
            logger.warning("Skipping repo entry missing repo or local_path: %s", r)
            continue
        branch = r.get("branch", "main")
        p_interval = r.get("poll_interval_seconds", poll_interval)
        d_seconds = r.get("debounce_seconds", debounce)

        t_poll = threading.Thread(
            target=github_poller.poll_loop,
            args=(repo, local_path, cfg.get("github_token"), branch, p_interval, stop),
            daemon=True,
        )
        t_poll.start()
        threads.append(t_poll)

        t_watch = threading.Thread(
            target=local_watcher.watch_loop,
            args=(
                local_path,
                d_seconds,
                user_name,
                user_email,
                cfg.get("github_token"),
                repo,
                branch,
                pull_before_push,
                stop,
            ),
            daemon=True,
        )
        t_watch.start()
        threads.append(t_watch)

    logger.info("GitSync started with %d repo(s)", len(cfg["repos"]))
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
