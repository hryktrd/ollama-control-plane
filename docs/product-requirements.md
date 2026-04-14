# Ollama Control Plane - Product Requirements Document

## 目的

社内または個人管理下の複数PC上でQwen CoderをOllama経由で動かし、中央サーバがそれらをエージェントプールとして管理し、Claude CodeおよびOpenAI互換APIクライアントから一貫した方法で利用できるようにする。

## システム全体像

システムは4要素で構成されます。

### 1. Agent Host
- 各PC上で動くローカル常駐プロセス
- OllamaとQwen Coderを実行ノードとして抱える
- Controllerへポーリングしてジョブを受け取る
- 登録時だけ管理者権限が必要、その後は短命トークン

### 2. Controller Server
- エージェント登録・認証・ジョブ配布
- 状態管理（エージェントのステータス、リソース状況）
- 監査ログ
- ジョブキュー管理

### 3. API Gateway/Proxy
- OpenAI互換API（/v1/chat/completions, /v1/responses, /v1/models）
- Claude Code向け接続（Anthropic互換エンドポイント）
- API key認証、レート制限
- ジョブをコントローラに投入し、適切なエージェントへルーティング

### 4. Client Integrations
- Claude Code
- 独自CLI
- Python / Nodeアプリケーション
- OpenAI SDK, Anthropic SDKを使用可能

## ユースケース

1. **分散推論** - 自宅PC上のQwen Coderを、別PCからローカルにいるように使用
2. **Claude Code統合** - Claude CodeからQwen Coderをモデルとして利用
3. **SDKを通じた呼び出し** - Python/NodeからOpenAI SDKで呼び出し
4. **分散ジョブ処理** - サーバ側でジョブをキューイングし、空いているエージェントへ配布
5. **モデル拡張性** - GemmaやLlama等、他モデルも同じ仕組みで差し替え可能

## 機能要件

### エージェント登録フロー

- Agent Hostは初回登録時に**招待トークン**（または登録用トークン）でControllerへ登録
- Controller払い出し項目：
  - `agent_id`: 一意のエージェント識別子
  - `pool_id`: 所属するプール
  - `listener_token`: 短命ポーリング用トークン
  - `refresh_token`: トークン更新用（オプション）
  - `poll_interval`: ポーリング間隔（秒）
  - `assigned_capabilities`: 利用可能モデル、ツール
  - `max_concurrency`: 最大同時実行数

- 登録後、管理者権限は永続保持しない
- 待受は短命トークン（JWT または定期ローテーション可能なトークン）に切り替え

### エージェント待受

- Agent HostはControllerへ**長周期ポーリング**またはハートビート付きポーリング
- 報告状態：
  - `online`, `idle`, `busy`, `offline`, `error`
  - CPU負荷率
  - GPU/VRAM使用状況
  - ロード済みモデル
  -実行中ジョブ数
  - ジョブキュー長

- Controllerはエージェントの**リソース情報を保持**し、スケジューリングに利用

### ジョブ実行

- **ジョブタイプ（最低実装）**：
  - `chat-completion`: LLMへの会話リクエスト
  - `responses`: バッチ応答処理
  - `embedding`: テキスト埋め込み
  - `tool-run`: 外部ツール呼び出し
  - `code-task`: Qwen Coder固有のタスク

- Agent HostはOllama APIに変換して実行
- 結果をControllerへ返却
- **ストリーミング応答に対応**

### OpenAI互換API

公開エンドポイント：
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /v1/models`

要件：
- OpenAI SDK の `base_url` 置き換えだけで動作
- API key認証（Bearer token）
- レート制限実装
- ストリーミング応答対応

### Claude Code接続

- Anthropic互換エンドポイント、またはOllama互換の中継を提供
- **論理モデル名** (`qwen3-coder`, `qwen-code-small` 等) で公開
- 裏側で各Agent Hostの実モデルへ透過的にルーティング

### Agent Pool管理

- 複数のAgent Poolを定義可能
  - 例: `desktop-gpu`, `laptop-cpu`, `high-memory`
- ジョブ投入時に指定可能な条件：
  - Pool ID
  - モデル名
  - 必要GPUメモリ（VRAM要件）
  - 優先度（normal, high, critical）
- スケジューラは条件に合うオンラインAgentへ配布

## 非機能要件

### セキュリティ

- Controller ↔ Agent間通信は**TLS必須**、可能なら**mTLS**対応
- 認証トークンの分離：
  - **登録トークン**: 初回登録のみ、高い権限（削除予定）
  - **待受トークン**: 短命JWT、ローテーション可能、PoolとAgentにバインド
  - **APIキー**: エンドユーザー用、OpenAI互換API呼び出し時
- OpenAI互換APIは**API key認証**、レート制限、監査ログ必須
- **Ollama本体は外部公開禁止** - Agent Hostローカルからのみ（127.0.0.1:11434）

### 可用性

- Controller停止時の戦略：
  - 新規ジョブ受付停止
  - 進行中ジョブは一時保留、自動再試行
  - タイムアウト後のリセット
- Agent Host再起動後：
  - 自動再接続
  - 再登録（既知のagent_idなら状態復帰）
  - 中断されたジョブの回復戦略

### 観測性

- **監査ログ記録** - 以下の情報を記録：
  - 呼び出し元ユーザー / APIキー
  - ターゲットモデル
  - ジョブID / タイプ
  - 実行時刻
  - 結果（成功/失敗）
  - トークン使用量（生成トークン、入力トークン）
- **メトリクス可視化**：
  - ジョブ実行時間分布
  - トークン消費量（日別、モデル別、ユーザー別）
  - ジョブ失敗率
  - Agent稼働率・リソース使用率

## データモデル概要

| エンティティ | 主要フィールド | 説明 |
|-------------|-------------|------|
| `users` | user_id, name, email, role, created_at | システムユーザー |
| `api_keys` | api_key_id, user_id, key_hash, scopes, rate_limit, created_at, expires_at | APIキー |
| `agent_pools` | pool_id, name, description, created_at | エージェントプール管理 |
| `agents` | agent_id, pool_id, hostname, status, capabilities, labels, max_concurrency, last_seen_at, resource_info | 登録済みエージェント |
| `models` | model_id, pool_id, name, version, ollama_name, max_input_tokens, max_output_tokens | モデル定義 |
| `jobs` | job_id, user_id, pool_id, model_id, job_type, status, priority, created_at, started_at, completed_at, agent_id | ジョブ記録 |
| `job_events` | event_id, job_id, event_type, status, timestamp, message | ジョブ進行状況 |
| `token_issues` | token_id, agent_id, token_type, expires_at, created_at | トークン管理 |
| `audit_logs` | log_id, timestamp, user_id, action, resource_type, resource_id, details | 監査ログ |

## 優先順位

### 優先度 1（MVP必須）
- Agent登録・認証・ポーリング
- OpenAI互換API（chat-completions）
- 単純なジョブディスパッチ

### 優先度 2（Phase 1-2）
- 複数Agent・Pool対応
- ストリーミング応答
- claude Code基本統合
- ジョブ優先度・スケジューリング

### 優先度 3（Phase 3）
- mTLS
- 詳細な監査ログ
- 管理UI
- 利用制限・配布ポリシー

### 優先度 4（Future）
- 複数モデルへの動的切り替え
- 課金・リソース配分
- 分析ダッシュボード
- アラート機能
