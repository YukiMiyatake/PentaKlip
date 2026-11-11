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

## 初回セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

cd web
npm install
cd ..
```

## 起動コマンド

### API

```powershell
.\.venv\Scripts\Activate.ps1
python -m pentaklip --reload
```

- API: http://127.0.0.1:8787
- Docs: http://127.0.0.1:8787/docs

### WebUI（開発）

別ターミナル:

```powershell
cd web
npm run dev
```

- UI: http://127.0.0.1:5173 （`/api` は 8787 へプロキシ）

### ビルド一体起動

```powershell
cd web
npm run build
cd ..
python -m pentaklip
```

- UI+API: http://127.0.0.1:8787/

## WebUI の主な画面

| タブ | 内容 |
|------|------|
| 置き換え | LoL フォルダの置き換え先を固定し、コピー元 .rofl を選んで上書きコピー（元ゲーム ID を DB 保存） |
| 自動切り分け | 録画動画 + イベント JSON からハイライト検出し ffmpeg で自動クリップ |
| ffmpeg | インストール（winget）と PATH 追加 |
| スタッツ / 表示設定 | 集計結果の表・グラフとレーン別表示設定 |

## リプレイ置き換え

1. **置き換え先**: `Documents\League of Legends\Replays` のローカル `.rofl` を選ぶ（選び直すまで固定）
2. 概要表示（試合時間・モード・プラクティス判定など。ROFL メタが読める場合）
3. **コピー元**: 前回フォルダを維持した一覧から選択 + 概要表示
4. **コピーして貼り付け**: 置き換え先 ID 名でコピー。元マッチ ID は DB に保存

API: `POST /api/replays/install`, `GET /api/replays/inspect`, `GET /api/ui/preferences`

## 自動クリップ切り分け

前提: 試合の録画ファイル、イベント JSON、ffmpeg

1. WebUI「ffmpeg」タブで導入 / PATH 追加
2. 「自動切り分け」タブで動画と events JSON を選択
3. ドライラン → 実行

API: `POST /api/clips/auto-split`（内部で検出 + `/api/clips/create`）

## パッケージ構成

```text
src/pentaklip/
  api/       FastAPI
  replay/    リネーム / メタデータ
  clips/     クリップ作成
  detect/    ハイライト検出
  tools/     ffmpeg セットアップ
  stats/     スタッツ
  export/    ffmpeg 切り出し
  store/     SQLite
web/         React UI
```
