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
- PR 作成時に `feature` / `fix` / `chore` / `docs` / `ci` のいずれかを **必ず付与**する（例: `gh pr create --label feature`）
- タイプラベル（`feature` / `fix` / `chore` / `docs` / `ci` のいずれか）付き・非 draft・CI 成功の PR は Actions が **即 squash マージ**する（`fix` のみでも可）
- ラベル無しだと PR label gate が失敗し自動マージされない
- 詳細は [`.github/LABELS.md`](.github/LABELS.md)

## 設定の保存場所

フォルダパスや直近のゲーム ID などは API データディレクトリの JSON で管理します（既定: `%LocalAppData%\PentaKlip\`）。

| ファイル | 内容 |
|----------|------|
| `ui_preferences.json` | 出力ベース、Replays / Highlights、ROFL、イベントフォルダ、last_game_id など |
| `ffmpeg_settings.json` | ffmpeg パス・エンコーダ・品質 |

UI からの更新は `PATCH /api/ui/preferences` で**送ったキーだけ**マージします（古い画面状態での全置換による消失を防ぐ）。GET レスポンスの `settings_path` で実ファイルパスを確認できます。

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
| 置き換え | LoL Replays フォルダ（パス表示・参照で変更・記憶）を置き換え先にし、ダウンロードした .rofl を上書きコピー（元ゲーム ID を DB 保存） |
| 自動切り分け | 録画動画 + イベント JSON からハイライト検出し ffmpeg で自動クリップ |
| ffmpeg | インストール先指定（参照）・フォルダ移動・PATH 追加・簡易設定（品質 / パス / webm自動変換） |
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

`.webm` は切り分け実行時に `{出力ベース}/Replay/` へ MP4 変換してからカットします（変換済みがあれば再利用）。

1. WebUI「ffmpeg」タブで導入 / PATH 追加
2. 「自動切り分け」タブで **出力ベース** を設定（配下に `Event` / `Replay` / `stats` / `Clip` を自動作成）。ゲームIDは次の優先順で自動取得:
   - 置き換え時に保存した **元マッチID**（DB）
   - ROFL メタの gameId（あれば）
   - ROFL メタ指紋 `rofl-…`（リネームしても不変）
   - ファイル名（最終手段）
3. リプレイを開いた状態で **試合を走査して取得** → JSON 保存
   （Replay API で先頭から高速再生し、Live Client イベントを蓄積。終端 Seek だけでは序盤が欠ける）
   → `game.cfg` の `[General]` に `EnableReplayApi=1` が必要
   → `{出力ベース}/Event/{ゲームID}_events.json`
   → 既定で `{出力ベース}/stats/{ゲームID}_stats_bundle.json` / `{ゲームID}_stats_aggregated.json` も保存
   → JSON は生イベントのまま。戦闘統合は切り分け時
4. 同じタブで動画と events JSON を選択し、ドライラン → 実行
   → クリップは `{出力ベース}/Clip/{ゲームID}/` へ（ファイル名に `1m05s-1m25s` のような時間帯）
   → 近いキル／オブジェクト（既定 25 秒以内）は **1 戦闘 = 1 クリップ** にマージ
   → ドライラン結果に「JSON 内のイベント種別」と「クリップ未使用の種別」を表示

API:

- `GET /api/events/live` … 現在位置の Live Client イベント（スナップショット）
- `POST /api/events/harvest` … リプレイ先頭から高速再生してイベント蓄積（`speed` 既定 16）
- `POST /api/events/export` … イベント JSON 保存（`harvest` / `include_stats` 既定 true）
- `POST /api/clips/auto-split` … 検出 + 切り出し（未指定時は `Clip/{ゲームID}` へ）

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

- `GET /api/replays/local` … ローカル Replays 内の `.rofl` 一覧（`directory` 任意。未指定時は記憶パス → LoL 既定）
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
- `POST /api/stats/charts` … グラフ化のみ（集計結果 + レーン別表示設定）。`radar` / `lane_compare` / `table` / `line`
  - レーダーは各プレイヤー（塗り）とレーン平均（点線）。API 位置キー `UTILITY` の表示名は **SUPPORT**
  - Live Client 制約: **GPM / GD15 / XPD15 は取得不可**。**DPM / DMG%** は終了画面データタブの `{game_id}_ss.png` を `stats/` に置けば OCR でマージ可能（キャラアイコン + KDA で紐づけ。Windows OCR: `pip install 'pentaklip[ocr]'`）。デフォルト軸は `CSM / KDA / KP% / CSD15 / LVLD15 / VSPM / CS@15 / Vision Score`（Towers / OBJ はデフォルト非表示）
  - `Gold (active)` は観戦中アクティブプレイヤーの所持金のみ（獲得ゴールドではない）
- `GET/PUT /api/stats/display-settings` … レーンごとに表示するスタッツを設定（ジャングルはオブジェクト・CS・ゴールド等を含むデフォルト）

### OBS オーバーレイ（Browser Source）

1. API + WebUI を起動し、スタッツ JSON があるフォルダを用意
2. OBS に **Browser Source** を追加し URL 例:
   - `http://127.0.0.1:5173/obs?dir=D:\path\to\stats&position=MIDDLE&refresh=30`（開発）
   - または一体配信時 `http://127.0.0.1:8787/obs?...`
3. OBS 側で **Shutdown source when not visible** は任意。背景透過はページ側で有効
4. クロマキーしたい場合は `&chroma=%2300FF00` を付与

クエリ: `dir`（フォルダ）, `position`（TOP/JUNGLE/…）, `player`（部分一致）, `refresh`（秒）, `chroma`
