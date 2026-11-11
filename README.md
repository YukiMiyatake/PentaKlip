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
- 上記タイプラベル付き PR は CI 成功後に自動で squash マージされる
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

| タブ | 内容 |
|------|------|
| 置き換え | LoL フォルダの置き換え先を固定し、コピー元 .rofl を選んで上書きコピー（元ゲーム ID を DB 保存） |
| 自動切り分け | 録画動画 + イベント JSON からハイライト検出し ffmpeg で自動クリップ |
| ffmpeg | インストール（winget）・PATH 追加・簡易設定（品質 / パス / webm自動変換） |
| スタッツ / 表示設定 | 集計結果の表・グラフとレーン別表示設定 |

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

## 自動クリップ切り分け

前提: 試合の録画ファイル（`.mp4` / `.webm` など）、イベント JSON、ffmpeg

`.webm` は切り分け実行時にゲームフォルダへ MP4 変換してからカットします（変換済みがあれば再利用）。

1. WebUI「ffmpeg」タブで導入 / PATH 追加
2. 「自動切り分け」タブで **出力ルート** を設定。ゲームIDは次の優先順で自動取得:
   - 置き換え時に保存した **元マッチID**（DB）
   - ROFL メタの gameId（あれば）
   - ROFL メタ指紋 `rofl-…`（リネームしても不変）
   - ファイル名（最終手段）
3. リプレイを終端まで Seek → **今すぐ取得** → JSON 保存
   （Live Client は現在時刻までのイベントを返す）
   → `{出力ルート}/{ゲームID}/events.json`（衝突時は `ID-1`）
   → JSON は生イベントのまま。戦闘統合は切り分け時
4. 同じタブで動画と events JSON を選択し、ドライラン → 実行
   → クリップも同じゲームフォルダへ（同名ファイルは `clip-1.mp4`）
   → 近いキル／オブジェクト（既定 25 秒以内）は **1 戦闘 = 1 クリップ** にマージ
   → ドライラン結果に「JSON 内のイベント種別」と「クリップ未使用の種別」を表示

API:

- `GET /api/events/live` … 現在の Live Client イベント
- `POST /api/events/export` … イベント JSON 保存（`game_id` 必須。`{ "Events": [...], "meta": {"game_id": ...} }`）
- `POST /api/clips/auto-split` … 検出 + 切り出し（未指定時はゲームIDフォルダへ）

## パッケージ構成

```text
src/pentaklip/
  api/       FastAPI
  replay/    .rofl リネーム / 配置・元マッチ ID
  detect/    ハイライト検出
  clips/     クリップ作成ジョブ
  events/    Live Client イベント JSON 出力
  record/    Replay / Live Client API
  tools/     ffmpeg セットアップ
  stats/     スタッツ収集 / 集計 / グラフ（分離）
  export/    ffmpeg 切り出し
  store/     SQLite
```

## リネーム（.rofl 配置）

ダウンロードしたリプレイを、自分のローカルリプレイ ID 名で LoL の Replays フォルダへ配置します。**元のマッチ ID は DB に保持**します。

```powershell
.\.venv\Scripts\Activate.ps1
python -m pentaklip --reload
```

例（PowerShell + curl）:

```powershell
curl -X POST http://127.0.0.1:8787/api/replays/install `
  -H "Content-Type: application/json" `
  -d '{
    "source_path": "C:\\Downloads\\KR-1234567890.rofl",
    "local_replay_id": "JP1-1111111111",
    "mode": "copy",
    "dry_run": false
  }'
```

| mode | 動作 |
|------|------|
| `copy` | コピーして配置（既定） |
| `move` | 移動して配置 |
| `rename_in_place` | 同じフォルダ内でファイル名だけ変更 |

関連 API:

- `GET /api/replays/local` … ローカル Replays 内の `.rofl` 一覧
- `GET /api/replays/parse-id?path=...` … ファイル名からマッチ ID を抽出
- `GET /api/replays` … DB に記録した配置履歴

## クリップ作成

前提:

1. 試合全体の録画動画がある（OBS 等。LoL クライアント自動録画は未実装）
2. 切り出し区間が分かる（手動秒数 / 検出済み highlights / Live Client の events）
3. `ffmpeg` が PATH にある

```powershell
# 手動区間で作成
curl -X POST http://127.0.0.1:8787/api/clips/create `
  -H "Content-Type: application/json" `
  -d '{
    "source_video_path": "C:\\Videos\\match.mp4",
    "original_match_id": "KR-1234567890",
    "segments": [
      {"start_sec": 110, "end_sec": 130, "kind": "kill", "label": "solo"}
    ]
  }'
```

イベントから自動検出して切る例:

```powershell
curl -X POST http://127.0.0.1:8787/api/clips/create `
  -H "Content-Type: application/json" `
  -d '{
    "source_video_path": "C:\\Videos\\match.mp4",
    "padding_before_sec": 10,
    "padding_after_sec": 10,
    "events": [
      {"EventName": "ChampionKill", "EventTime": 120.0}
    ]
  }'
```

出力先既定: `%LOCALAPPDATA%\PentaKlip\clips`  
一覧: `GET /api/clips`  
試行のみ: `"dry_run": true`

## スタッツ API（概要）

- `POST /api/stats/sessions` → ingest/poll → finalize（JSON/YAML 出力可）
- `POST /api/stats/aggregate` … 集計のみ
- `POST /api/stats/charts` … グラフ化のみ（集計結果 + レーン別表示設定）
- `GET/PUT /api/stats/display-settings` … レーンごとに表示するスタッツを設定
