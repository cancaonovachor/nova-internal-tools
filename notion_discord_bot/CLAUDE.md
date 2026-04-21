# CLAUDE.md — notion_discord_bot

Notion webhook を受け取り Discord に通知する内部ツール。詳細設計は `architecture.md`、利用者向けは `README.md` を参照。このファイルは Claude Code 用の開発補助メモ。

## 構成の要点

- **ingress (Cloud Run)**: webhook 受信 / 署名検証 / event type filter / Cloud Tasks への投入
- **Cloud Tasks queue**: リトライ + task name (event_id ベース) で at-least-once 重複排除
- **worker (Cloud Run)**: Cloud Tasks → Notion API で enrich → Discord へ送信
- 両サービスは **同一コンテナイメージ**、Cloud Run 側で `args` を切り替えている (`deploy/Dockerfile` の ENTRYPOINT は `uv run uvicorn` 固定、args で `ingress.main:app` or `worker.main:app`)

## ローカル開発

```bash
uv sync
cp .env.example .env   # NOTION_VERIFICATION_TOKEN / NOTION_API_KEY を設定
# 3 ターミナル
uv run uvicorn worker.main:app  --reload --port 8081
uv run uvicorn ingress.main:app --reload --port 8080
ngrok http 8080
```

ingress は `CLOUD_TASKS_QUEUE` 未設定時に `HTTPDirectEnqueuer` を使い、`WORKER_URL` (default `http://localhost:8081/tasks/notion-event`) に直接 POST する。本番はこの env が揃うと自動で `CloudTasksEnqueuer` になる。

## 本番デプロイ手順

1. 新イメージ push: `gcloud builds submit . --config deploy/cloudbuild.yaml`
2. Terraform apply (`infra/notion_discord_bot/`) で env 変更等を反映
3. **Cloud Run リビジョン強制が必要なケース** (後述) は `gcloud run deploy --image=<latest>` で push する

### 初回 apply の流れ

Cloud Run 作成時点でイメージが Artifact Registry に存在していないと失敗する。さらに secret に version が無い状態で Cloud Run が起動しようとすると失敗するため、secret resource → `gcloud secrets versions add` → image push → apply の順で走らせる。詳細は `infra/notion_discord_bot/README.md` 参照。

```bash
# 1) APIs / AR / secrets / queue / SA を先行 (module 経由なので module.artifact_registry を target)
cd infra/notion_discord_bot
terraform apply \
  -target=google_project_service.apis \
  -target=module.artifact_registry \
  -target=google_secret_manager_secret.verification_token \
  -target=google_secret_manager_secret.api_key \
  -target=google_secret_manager_secret.discord_webhook \
  -target=google_secret_manager_secret.discord_deletion_webhook \
  -target=google_cloud_tasks_queue.queue \
  -target=google_service_account.ingress \
  -target=google_service_account.worker \
  -target=google_service_account_iam_member.ingress_self_user

# 2) secret version を投入 (tfvars は使わない)
printf %s "$TOKEN" | gcloud secrets versions add notion-api-key --data-file=- --project=starlit-road-203901
# ...他の secret も同様

# 3) イメージを build/push
cd ../../notion_discord_bot
gcloud builds submit . --config deploy/cloudbuild.yaml

# 4) 残り全部
cd ../infra/notion_discord_bot
terraform apply
```

state backend は **GCS (`gs://starlit-road-203901-tfstate`, prefix `notion-discord-bot`)**。tfvars ファイルは作らない方針 (root CLAUDE.md の feedback 参照)。secret 値は `gcloud secrets versions add` でアウトオブバンドに投入する。

## 作業時の落とし穴 (本セッションで踏んだもの)

### 1. `/healthz` は Cloud Run 側で予約パス
- Cloud Run v2 の前段で `/healthz` は intercept されアプリに届かず 404 になる
- ヘルスチェックは `/health` 等で定義する (ingress / worker とも `@app.get("/health")`)

### 2. Cloud Run v2 の memory は 512Mi 以上
- CPU=1 で memory=256Mi は Cloud Run のバリデーションで弾かれる (`Total memory < 512 Mi is not supported with cpu always allocated`)
- resources.limits.memory は最低 512Mi にしておく

### 3. Secret の `:latest` ref は自動 refresh されない
- Secret Manager に新 version を追加しても、Cloud Run のランタイムは **新リビジョンが作られるまで** 古い値をキャッシュする
- Terraform の `google_secret_manager_secret_version` 更新だけだと Cloud Run v2 は "Modifications complete after 0s" (≈no-op) になり新リビジョンが出ない
- **解決**: `gcloud run deploy notion-discord-bot-<name> --image=<same image> --region=asia-northeast1` で新リビジョンを強制するのが一番確実
- 代替: Terraform で `version = "latest"` → 特定 version 番号に変更すれば Cloud Run 差分 → 新リビジョン

### 4. `terraform apply -replace=cloud_run_v2_service` は IAM bindings を落とす
- Cloud Run サービスを replace すると、`google_cloud_run_v2_service_iam_member` の state が無効になり `allUsers` の invoker や ingress→worker 間の invoker が消える
- `-replace` する時は **IAM member も一緒に `-replace` 対象** に含める:
  ```
  terraform apply \
    -replace=google_cloud_run_v2_service.ingress \
    -replace=google_cloud_run_v2_service_iam_member.ingress_public \
    -replace=google_cloud_run_v2_service_iam_member.ingress_invokes_worker
  ```

### 5. Secret Manager の名前衝突 (共有 GCP project)
- `discord-webhook-url` のような汎用名は既存のものと衝突しやすい
- このツール由来の secret は **`notion-bot-`** prefix を付けている (例: `notion-bot-discord-webhook`)
- ただし `notion-verification-token` / `notion-api-key` は prefix 無しで作ってしまった (歴史的理由)。新規追加時は prefix を付けること

### 6. Notion webhook verification token は subscription 毎に違う
- Notion 側で webhook URL を変更 / 新規作成すると、**毎回別の verification_token が発行される**
- 初回 POST に verification_token が載ってくるので ingress のログから拾う:
  ```bash
  gcloud run services logs read notion-discord-bot-ingress --region=asia-northeast1 --limit=50 \
    | grep verification_token
  ```
- 拾った値を Notion UI に貼り付け＆ Secret Manager `notion-verification-token` を更新 → ingress を `gcloud run deploy` で新リビジョン化 → 署名検証が新 token で有効化

### 7. child_page / child_database ブロックは rich_text じゃなく title
- 通常のブロック (paragraph, heading_2 など) は `content.rich_text[]` に本文が入る
- `child_page` / `child_database` は `content.title` (string) にタイトルが入る
- `extract_block_text` は両方を見て返す。新しいブロック型を追加したくなったら Notion API ドキュメントで該当 content の構造を確認すること

### 8. `format_event` は dict (Discord webhook payload) を返す
- 昔は `str` を返して `content` field に入れていたが、embed 化のため **dict を返す**ようになった
- 返り値の構造: `{"content": "...", "embeds": [{"fields": [...]}]}`
- sender (`DiscordSender` protocol) の `send()` も `dict` を受ける。`FileDiscordSender` はローカル用に `render_payload_as_text` で読める形に展開してファイルに書く
- embed field の制限: name 256 字 / value 1024 字 / fields 25 個。超える場合 truncate かスライスする

### 9. ログ severity 設計 (Error Reporting / アラート連動)
`gcp_alert_discord_bot` 側の alert policy が `severity>=ERROR AND NOT httpRequest.status:*` で拾う前提なので、**WARNING と ERROR を意図的に使い分けている**:

- **NotionClient**: `urllib3.Retry` アダプタで transient 失敗 (connect/read timeout, 429, 5xx) を 3 回まで自動リトライ。リトライ中の urllib3 ログは WARNING なので Error Reporting 非対象
- **`enrich_event`** の except は `requests.RequestException` で広く拾って `logger.warning`。リトライ枯渇しても traceback を出さない (raw event で Discord 送信継続する fallback あり)
- **`WebhookDiscordSender`**: 429 は `Retry-After` 尊重、5xx は指数バックオフで 3 回まで in-process リトライ
- **Discord 送信失敗時の severity 切替**: `worker/main.py` で `X-CloudTasks-TaskRetryCount` ヘッダを見て、`CLOUD_TASKS_ERROR_RETRY_THRESHOLD` (既定 4 = queue の max_attempts-1) 未満は `logger.warning`、最終試行のみ `logger.exception`。これにより Cloud Tasks がリトライで救済したケースは Error Reporting に上がらない

新しい例外経路を追加する時はこの方針を踏襲: "リトライで救われる見込み" は warning、"本当に捨てる" 最終段階のみ exception。

## リポジトリ内の主な場所

| パス | 役割 |
|---|---|
| `ingress/main.py` | FastAPI: `/webhook/notion` で受け取り Cloud Tasks に投げる |
| `worker/main.py` | FastAPI: `/tasks/notion-event` で enrich + Discord 送信 |
| `common/signature.py` | `X-Notion-Signature` HMAC-SHA256 検証 |
| `common/task_enqueuer.py` | `HTTPDirectEnqueuer` (local) / `CloudTasksEnqueuer` (prod) の切り替え |
| `common/notion_client.py` | Notion REST クライアント + `enrich_event` + property/block 値抽出 |
| `common/discord_format.py` | enriched event → Discord webhook payload dict (content + embeds.fields) |
| `common/discord_sender.py` | `FileDiscordSender` (local stub) / `WebhookDiscordSender` (prod) + `render_payload_as_text` |
| `deploy/Dockerfile` | ingress/worker 共用。Cloud Run 側で args 切替 |
| `deploy/cloudbuild.yaml` | Cloud Build 設定。`-f deploy/Dockerfile` で build |
| `../infra/notion_discord_bot/` | GCP 全リソース定義 (Cloud Run x2, Cloud Tasks, AR, Secret Manager, IAM, SA)。Artifact Registry は `infra/modules/artifact_registry` を参照 |

## コード規約

- Python 3.12+、`uv` で依存管理
- FastAPI + `uvicorn[standard]`
- Notion / Discord へのアクセスは `requests` (同期)。FastAPI の `BackgroundTasks` で ack を即返し、enqueue や enrich を非同期化
- ログは標準ライブラリ `logging`。Cloud Run の stdout/stderr を素直に使う
- secrets は **環境変数経由** でコードに渡す (Secret Manager → Cloud Run env)
- 整形の見た目を変える時は `common/discord_format.py::format_event` にテスト用のサンプルを当ててから push する (`uv run python -c "from common.discord_format import format_event; print(format_event({...}))"`)

## イベント種別による送信先ルーティング

worker は `default_sender` と `deletion_sender` の 2 本を持っている:

- **`default_sender`**: 全イベントを送る。`DISCORD_WEBHOOK_URL` 未設定ならローカル用 `FileDiscordSender`
- **`deletion_sender`**: `page.deleted` のときだけ **追加で** 送る 2 本目の webhook。`DISCORD_DELETION_WEBHOOK_URL` が設定されていれば有効

イベント種別ごとに送り先を増やしたい時はこのパターンを踏襲する:
1. `common/discord_sender.py` の protocol は payload dict を受け取るだけなので変更不要
2. `worker/main.py` に `<event>_sender` 変数を追加、env から URL を読む
3. `handle_notion_event` で `event_type` を見て該当 sender にも送る
4. Terraform に secret + env + IAM binding を足す (既存 `discord_deletion_webhook` ブロックが雛形)

## 今後の拡張候補 (architecture.md priority 4 以降)

- **デバウンス** (`page_id` 単位の短時間集約): Firestore 等が必要。同一ページで連続更新があるとスパムになる場合に導入
- **before/after 表示**: webhook payload には before 値が入らないので、Firestore に last-seen スナップショットを保持する必要あり。ユーザーは "Empty → 値" 表記を希望していた
- **イベントフィルタの細分化**: 現在は event type の allowlist のみ。特定の database / page だけ通知するようなルール定義が必要になったら config 化
