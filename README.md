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

## 初回セットアップ

```powershell
# Python API
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# WebUI
cd web
npm install
cd ..
```

## 起動コマンド

### 1. API サーバー（FastAPI / Python）

```powershell
.\.venv\Scripts\Activate.ps1
python -m pentaklip --reload
```

| 項目 | 値 |
|------|-----|
| URL | http://127.0.0.1:8787 |
| ヘルスチェック | http://127.0.0.1:8787/api/health |
| OpenAPI | http://127.0.0.1:8787/docs |

ホスト / ポート変更例:

```powershell
python -m pentaklip --host 127.0.0.1 --port 8787 --reload
```

### 2. WebUI（開発: Vite + React）

API を起動した状態で、別ターミナルから:

```powershell
cd web
npm run dev
```

| 項目 | 値 |
|------|-----|
| URL | http://127.0.0.1:5173 |
| API プロキシ | `/api` → `http://127.0.0.1:8787` |

### 3. API + WebUI（ビルド済み静的配信）

Web をビルドすると、API と同じプロセスで UI も配信します。

```powershell
cd web
npm run build
cd ..
.\.venv\Scripts\Activate.ps1
python -m pentaklip
```

| 項目 | 値 |
|------|-----|
| UI | http://127.0.0.1:8787/ |
| API | http://127.0.0.1:8787/api/... |

### 4. テスト / チェック

```powershell
# Python
.\.venv\Scripts\Activate.ps1
pytest
ruff check src tests

# Web ビルド確認
cd web
npm run build
```

### 未実装（予定）

| アプリ | 状態 |
|--------|------|
| Tauri デスクトップ殻 | 未実装（正式配布時。同じ React UI を包む想定） |

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
