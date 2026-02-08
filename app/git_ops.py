"""
Git operations: clone, pull, add, commit, push.
Uses HTTPS with token for private repo support.
"""
import os
import subprocess
import logging

logger = logging.getLogger(__name__)


def _repo_url_with_token(repo: str, token: str | None) -> str:
    """Build HTTPS URL with token for auth."""
    repo = repo.strip()
    if repo.startswith("https://"):
        url = repo
    elif repo.startswith("git@"):
        logger.warning("SSH URLs not supported; use HTTPS with owner/repo format")
        return repo
    else:
        url = f"https://github.com/{repo}.git"
    if token and "github.com" in url:
        url = url.replace("https://", f"https://{token}@")
    return url


def _run_git(cwd: str, args: list[str], env: dict | None = None) -> tuple[int, str, str]:
    """Run git command, return (returncode, stdout, stderr)."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=full_env,
            timeout=120,
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        logger.error("Git command timed out: git %s", " ".join(args))
        return -1, "", "Timeout"


def clone(repo: str, local_path: str, token: str | None, branch: str = "main") -> bool:
    """Clone repo into local_path. Returns True on success."""
    url = _repo_url_with_token(repo, token)
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    code, out, err = _run_git(".", ["clone", "--depth", "1", "-b", branch, url, local_path])
    if code != 0:
        # Try default branch if specified branch doesn't exist
        if "not found" in err.lower() or "couldn't find" in err.lower():
            code2, _, _ = _run_git(".", ["clone", "--depth", "1", url, local_path])
            if code2 == 0:
                return True
        logger.error("Clone failed: %s", err)
        return False
    return True


def _set_remote_url(local_path: str, repo: str, token: str | None) -> None:
    """Ensure remote origin URL uses current token."""
    url = _repo_url_with_token(repo, token)
    _run_git(local_path, ["remote", "set-url", "origin", url])


def pull(local_path: str, token: str | None, repo: str | None = None) -> bool:
    """Pull latest changes. Returns True on success. Pass repo to refresh remote URL with token."""
    if repo and token:
        _set_remote_url(local_path, repo, token)
    code, out, err = _run_git(local_path, ["pull"])
    if code != 0:
        logger.error("Pull failed in %s: %s", local_path, err)
        return False
    return True


def add_all(local_path: str) -> bool:
    """Stage all changes."""
    code, _, err = _run_git(local_path, ["add", "-A"])
    if code != 0:
        logger.error("Git add failed: %s", err)
        return False
    return True


def has_changes(local_path: str) -> bool:
    """Return True if there are staged or unstaged changes."""
    code, out, _ = _run_git(local_path, ["status", "--porcelain"])
    return code == 0 and bool(out.strip())


def commit(local_path: str, message: str, user_name: str, user_email: str) -> bool:
    """Create commit with configured user."""
    env = {"GIT_AUTHOR_NAME": user_name, "GIT_AUTHOR_EMAIL": user_email}
    code, _, err = _run_git(
        local_path,
        ["commit", "-m", message],
        env=env,
    )
    if code != 0:
        if "nothing to commit" in err:
            return True
        logger.error("Commit failed: %s", err)
        return False
    return True


def push(local_path: str, token: str | None, branch: str | None = None, repo: str | None = None) -> bool:
    """Push to remote. Pass repo to refresh remote URL with token."""
    if repo and token:
        _set_remote_url(local_path, repo, token)
    args = ["push"]
    if branch:
        args.extend(["origin", branch])
    code, _, err = _run_git(local_path, args)
    if code != 0:
        logger.error("Push failed in %s: %s", local_path, err)
        return False
    return True


def is_git_repo(path: str) -> bool:
    """Return True if path is a git repository."""
    git_dir = os.path.join(path, ".git")
    return os.path.isdir(git_dir)


def get_default_branch(local_path: str) -> str:
    """Get default branch (e.g. main or master)."""
    code, out, _ = _run_git(local_path, ["rev-parse", "--abbrev-ref", "HEAD"])
    if code == 0 and out.strip():
        return out.strip()
    return "main"


def pull_before_push(local_path: str, repo: str | None = None, token: str | None = None) -> bool:
    """Pull with rebase to integrate remote changes before push."""
    if repo and token:
        _set_remote_url(local_path, repo, token)
    code, _, err = _run_git(local_path, ["pull", "--rebase"])
    if code != 0:
        logger.error("Pull --rebase failed: %s", err)
        return False
    return True
