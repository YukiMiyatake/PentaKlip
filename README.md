# PentaKlip

LoL リプレイからキル・集団戦などのハイライトを検出し、クリップ動画として書き出す Windows 向けツール。

企画・技術選定は [docs/企画.md](docs/企画.md) を参照。

## 技術スタック（要約）

| 層 | 技術 |
|----|------|
| コア | Python 3.12 |
| API | FastAPI |
| UI（MVP） | React + Vite（ローカル WebUI） |
| UI（正式） | Tauri 2 + 同じ React |
| 動画 | ffmpeg |
| DB | SQLite |

## 開発フロー

- タスクごとに `feature/<名前>` ブランチを切り、`main` へ PR する（[`.cursor/rules/pr-per-task.mdc`](.cursor/rules/pr-per-task.mdc)）
- PR には `feature` / `fix` / `chore` / `docs` / `ci` のいずれかのラベルが必要
- `auto-merge` ラベル付き PR は CI 成功後に squash マージされる
- 詳細は [`.github/LABELS.md`](.github/LABELS.md)

## 開発セットアップ


```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

API 起動:

```powershell
python -m pentaklip --reload
```

ヘルスチェック: `http://127.0.0.1:8787/api/health`

テスト:

```powershell
pytest
```

## パッケージ構成

```text
src/pentaklip/
  api/       FastAPI
  replay/    .rofl 配置・元マッチ ID
  detect/    ハイライト検出
  record/    Replay / Live Client API
  stats/     スタッツ収集 / 集計 / グラフ（分離）
  export/    ffmpeg 切り出し
  store/     SQLite
```

## スタッツ API（概要）

- `POST /api/stats/sessions` → ingest/poll → finalize（JSON/YAML 出力可）
- `POST /api/stats/aggregate` … 集計のみ
- `POST /api/stats/charts` … グラフ化のみ（集計結果 + レーン別表示設定）
- `GET/PUT /api/stats/display-settings` … レーンごとに表示するスタッツを設定
