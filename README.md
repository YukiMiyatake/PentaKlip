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
  replay/    .rofl リネーム / 配置・元マッチ ID
  detect/    ハイライト検出
  clips/     クリップ作成ジョブ
  record/    Replay / Live Client API
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
