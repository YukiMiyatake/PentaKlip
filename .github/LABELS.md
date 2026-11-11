# Repository labels

Create these labels in GitHub (Settings → Labels) if they do not exist:

| Name | Purpose |
|------|---------|
| `feature` | New capability |
| `fix` | Bug fix |
| `chore` | Maintenance |
| `docs` | Documentation only |
| `ci` | CI / workflow / tooling |
| `dependencies` | Dependabot |
| `auto-merge` | Enable squash auto-merge when CI is green |

CI job **PR label gate** requires one of: `feature`, `fix`, `chore`, `docs`, `ci`.

## Repo setup

Run (admin):

```powershell
.\.github\scripts\setup-repo.ps1
```

Notes:

- Squash merge + delete branch on merge are enabled via script / `gh repo edit`
- **Branch protection** and **auto-merge** on a **private** repo need **GitHub Pro** (or make the repo public). Workflows still run without protection; merges are manual until then.
