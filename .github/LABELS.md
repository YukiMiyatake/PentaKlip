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

## Auto-merge contract

1. Agent / human opens a PR with a type label (`gh pr create --label feature …`).
2. Workflow **Auto merge** enables squash auto-merge on labeled, non-draft PRs.
3. When **CI** succeeds, the same workflow merges (or completes the queued auto-merge).
4. No type label → gate fails → **no auto-merge**. Do not leave PRs unlabeled.
5. If the PR is behind `main`, update the branch so checks can finish and merge.

Agents must not rely on manual merge; labeling + green CI is the merge path.

## Repo setup

Run (admin):

```powershell
.\.github\scripts\setup-repo.ps1
```

Notes:

- Squash merge + delete branch on merge are enabled via script / `gh repo edit`
- **Branch protection** and **auto-merge** on a **private** repo need **GitHub Pro** (or make the repo public). Workflows still run without protection; the merge-when-green job can still squash-merge labeled PRs with `GITHUB_TOKEN` when permissions allow.
