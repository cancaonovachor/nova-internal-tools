# CLAUDE.md — nova-internal-tools

CancaoNova 内部向けツール群の monorepo。各ツールは独立したサブディレクトリで自分の `uv` 環境を持つ。

## ツール

| ディレクトリ | 概要 |
|---|---|
| `choral_rss_bot/` | 合唱関連の RSS/Web スクレイピング + LLM 要約 + Discord 通知。Cloud Run Jobs + Cloud Scheduler で定期実行 |
| `notion_discord_bot/` | Notion webhook を受け取って Discord に通知。Cloud Run (ingress + worker) + Cloud Tasks |
| `gcp_alert_discord_bot/` | GCP Billing Budget / Cloud Monitoring アラートを Pub/Sub 経由で受けて Discord に通知。Cloud Run 単体 |

ツール固有の詳細はそれぞれの `<tool>/CLAUDE.md` を参照。

## 共通事項

- **Python 3.12+ / uv**。各ツールが自前の `pyproject.toml` と `.venv`
- **GCP**: プロジェクト `starlit-road-203901` (asia-northeast1 中心)
- **Terraform backend**: `gs://starlit-road-203901-tfstate`、prefix はツール名 (例: `notion-discord-bot`)
- **branch 戦略**: `feat/<topic>` から `main` への PR。merge は PR 経由
- **commit message**: 日本語 + conventional prefix (`feat:`, `fix:`, `chore:` 等)。Co-Authored-By で Claude を併記する慣例あり

## 作業時の指針

- 各ツールで `cd <tool>` してから `uv run ...` で実行する
- 新規ツールを足す時は、既存 (`choral_rss_bot`, `notion_discord_bot`) の構成を参考にする
- GCP リソースを触る作業は **破壊的操作前に必ず確認**。`terraform apply` はユーザーに plan を見せてから承認をもらう
