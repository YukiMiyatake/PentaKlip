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
  export/    ffmpeg 切り出し
  store/     SQLite
```
