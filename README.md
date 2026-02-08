# GitSync

A Docker service that syncs GitHub repos with local directories:

- **GitHub → local**: Polls for new commits and pulls to the local path.
- **Local → GitHub**: Watches for file changes, waits a debounce period, then commits and pushes.

Designed for syncing Obsidian vaults between GitHub and Nextcloud, but works for any repo/directory pair.

## Quick Start

1. Create config directory and copy example:

   ```bash
   mkdir -p config data/obsidian
   cp config.json.example config/config.json
   ```

2. Edit `config/config.json`:
   - Set `github_token` (required for private repos).
   - Add your repo and local path mappings.

3. Run with Docker Compose:

   ```bash
   docker compose up -d
   ```

## Configuration

`config/config.json`:

| Key                    | Description                                 | Default  |
|------------------------|---------------------------------------------|----------|
| `github_token`         | GitHub PAT (classic or fine-grained). Leave empty for public repos. | -        |
| `poll_interval_seconds`| How often to check GitHub for new commits   | 60       |
| `debounce_seconds`     | Wait time after last local change before commit+push | 30 |
| `git_user_name`        | Author name for commits                     | GitSync  |
| `git_user_email`       | Author email for commits                    | gitsync@local |
| `pull_before_push`     | Pull with rebase before pushing             | true     |
| `repos`                | Array of `{ repo, local_path, ... }`        | required |

Per-repo overrides: `poll_interval_seconds`, `debounce_seconds`, `branch` (default `main`).

Example:

```json
{
  "github_token": "ghp_xxxx",
  "poll_interval_seconds": 60,
  "debounce_seconds": 30,
  "repos": [
    { "repo": "owner/obsidian-vault", "local_path": "/data/obsidian" },
    { "repo": "owner/other", "local_path": "/data/other", "debounce_seconds": 60 }
  ]
}
```

## Docker Compose

Ensure `local_path` in config matches container paths. Example volume mapping:

```yaml
volumes:
  - ./config:/config
  - ./data/obsidian:/data/obsidian
```

To sync multiple directories, add more volumes and matching entries in `repos`:

```yaml
volumes:
  - ./config:/config
  - ./data/vault1:/data/vault1
  - ./data/vault2:/data/vault2
```

```json
"repos": [
  { "repo": "owner/vault1", "local_path": "/data/vault1" },
  { "repo": "owner/vault2", "local_path": "/data/vault2" }
]
```

## Obsidian + Nextcloud

1. Mount your Nextcloud sync directory (e.g. Obsidian vault) as the `local_path` volume.
2. Point `repo` to the GitHub repo for that vault.
3. GitSync will pull GitHub changes into the local path and push local edits back after the debounce delay.

## Security

- Store `github_token` in config or pass via `GITHUB_TOKEN` env var (recommended for shared configs).
- Do not commit `config/config.json` with tokens.
- For TrueNAS, use Docker secrets or env vars if available.

## Build

```bash
docker compose build
docker compose up -d
```
