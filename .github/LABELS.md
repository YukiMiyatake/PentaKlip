# Repository labels and auto-merge

## Type labels (required on every PR)

Create these in GitHub (Settings → Labels) if missing:

| Name | Purpose |
|------|---------|
| `feature` | New capability |
| `fix` | Bug fix |
| `chore` | Maintenance |
| `docs` | Documentation only |
| `ci` | CI / workflow / tooling |
| `dependencies` | Dependabot |

CI job **PR label gate** fails unless the PR has one of: `feature`, `fix`, `chore`, `docs`, `ci`.

Any of those labels is enough — **`fix` alone is valid** and must auto-merge the same as `feature`.

## Auto-merge contract

1. Agent / human opens a PR with a type label (`gh pr create --label fix …`).
2. Workflow **Auto merge** queues GitHub auto-merge while CI runs.
3. When **CI** succeeds, the same workflow **squash-merges immediately** (does not stop at `--auto`).
4. If the PR is **BEHIND** `main`, the workflow runs `gh pr update-branch` and waits for the next green CI, then merges.
5. A 15-minute cron sweep retries open typed PRs that got stuck.
6. No type label → gate fails → **no auto-merge**.

Agents must not leave PRs unlabeled. Prefer letting Actions merge; if a PR stays open after green CI + label, update from main or re-run the Auto merge workflow.

## Repo setup

Run (admin):

```powershell
.\.github\scripts\setup-repo.ps1
```

Notes:

- Squash merge + delete branch on merge are enabled via script / `gh repo edit`
- GitHub-native `--auto` alone is unreliable on private free plans and when the branch is behind; this repo’s Actions job performs the real squash merge after CI is green
