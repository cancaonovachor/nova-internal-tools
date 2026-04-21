# CLAUDE.md — nova-internal-tools

CancaoNova 内部向けツール群の monorepo。各ツールは独立したサブディレクトリで自分の `uv` 環境を持つ。

## ツール

| ディレクトリ | 概要 |
|---|---|
| `choral_rss_bot/` | 合唱関連の RSS/Web スクレイピング + LLM 要約 + Discord 通知。Cloud Run Jobs + Cloud Scheduler で定期実行 |
| `notion_discord_bot/` | Notion webhook を受け取って Discord に通知。Cloud Run (ingress + worker) + Cloud Tasks |
| `gcp_alert_discord_bot/` | GCP Billing Budget / Cloud Monitoring アラートを Pub/Sub 経由で受けて Discord に通知。Cloud Run 単体 |

ツール固有の詳細はそれぞれの `<tool>/CLAUDE.md` を参照。

## インフラ (Terraform)

GCP リソース定義はすべて `infra/` 配下に集約:

| パス | 役割 |
|---|---|
| `infra/modules/artifact_registry/` | 共通 Artifact Registry リポジトリ module |
| `infra/modules/github_deployer_sa/` | tool 別 GitHub Actions deployer SA (main ref 専用) module |
| `infra/github_wif/` | WIF pool/provider + 共通 planner SA (PR plan 用 read-only) |
| `infra/notion_discord_bot/` | notion-discord-bot の Cloud Run x2 / Cloud Tasks / Secret Manager など |
| `infra/gcp_alert_discord_bot/` | gcp-alert-discord-bot 本体 + 他ツールのエラー監視 alert policy |

各ツールの state backend は GCS (`gs://starlit-road-203901-tfstate`) / prefix はツール名ごとに分離 (`notion-discord-bot` / `gcp-alert-discord-bot` / `github-wif`)。

**CI の役割分離** (`.github/workflows/`):

- `deploy-*.yaml`: push to main で image build + Cloud Run 更新。WIF → 各 tool deployer SA (write)
- `terraform-plan.yaml`: `infra/**` の PR で `terraform plan` を走らせ結果を PR コメント化。WIF → 共通 planner SA (read-only)
- `terraform-apply.yaml`: `workflow_dispatch` で stack を選択して `terraform apply`。WIF → 共通 applier SA。PR merge だけでは apply されず、Actions タブから手動キックが必要

WIF pool provider の `attribute_condition` は `(ref=main への push) OR (pull_request イベント)` を許可し、どれに向かうかは各 SA の IAM binding で絞る:
- deployer: subject を `ref:refs/heads/main` に固定 (PR からは借りられない)
- planner: `attribute.repository` で広く許可 (read-only なので PR 実行も可)
- applier: `attribute.event_name/workflow_dispatch` で絞る (push / pull_request からは借りられない。手動キック専用)

`github_wif` stack 自体 (applier SA を含む WIF 周り) は `terraform-apply.yaml` の対象外。self-modify 事故回避のため、WIF 変更は従来通りローカル apply で運用する。

## 共通事項

- **Python 3.12+ / uv**。各ツールが自前の `pyproject.toml` と `.venv`
- **GCP**: プロジェクト `starlit-road-203901` (asia-northeast1 中心)
- **branch 戦略**: `feat/<topic>` から `main` への PR。merge は PR 経由
- **commit message**: 日本語 + conventional prefix (`feat:`, `fix:`, `chore:` 等)。Co-Authored-By で Claude を併記する慣例あり

## 作業時の指針

- 各ツールで `cd <tool>` してから `uv run ...` で実行する
- 新規ツールを足す時は、既存 (`choral_rss_bot`, `notion_discord_bot`) の構成を参考にする
- GCP リソースを触る作業は **破壊的操作前に必ず確認**。`terraform apply` は PR 承認 + merge 後に GitHub Actions `Terraform Apply` を手動キックして実行する (`workflow_dispatch`)。初回 bootstrap と `github_wif` stack のみローカル apply
