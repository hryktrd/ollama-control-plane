# Ollama Control Plane - Architecture Document

## 全体システムアーキテクチャ図

```
┌──────────────────────────────────────────────────────────────┐
│                     External Clients                          │
├──────────┬──────────────────────────┬──────────────────────┤
│ Claude   │  Python / Node.js Apps   │     Custom CLI        │
│  Code    │  (with OpenAI SDK)       │                       │
└────┬─────┴──────────────┬───────────┴──────────┬─────────────┘
     │                    │                      │
     └────────────────┬───┴──────────────────────┘
                      │
        ┌─────────────▼─────────────┐
        │   API Gateway / Proxy     │
        │  (OpenAI / Anthropic      │
        │   Compatible Endpoints)   │
        │  - Auth (API keys)        │
        │  - Rate limiting          │
        │  - Job queueing           │
        │  - Stream proxying        │
        └────────────────┬──────────┘
                         │
                         │ gRPC / HTTP
                         │
        ┌────────────────▼──────────────────┐
        │   Controller Server                │
        ├────────────────────────────────────┤
        │ - Agent registration & auth        │
        │ - Job queue & distribution         │
        │ - State management                 │
        │ - Audit logging                    │
        │ - Model registry                   │
        │ - Pool management                  │
        │ - Resource tracking                │
        │                                    │
        │ Database:                          │
        │ [PostgreSQL / SQLite]              │
        │ - agents, pools, jobs,             │
        │   tokens, audit_logs               │
        └────────────────┬───────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
    │ Agent   │    │ Agent   │    │ Agent   │
    │ Host 1  │    │ Host 2  │    │ Host N  │
    │ (PC-A)  │    │ (PC-B)  │    │ (PC-N)  │
    ├─────────┤    ├─────────┤    ├─────────┤
    │ Poller  │    │ Poller  │    │ Poller  │
    │ +       │    │ +       │    │ +       │
    │ Ollama  │    │ Ollama  │    │ Ollama  │
    │14b+GPU  │    │7b+CPU   │    │mistral  │
    │(qwen-   │    │(qwen-   │    │(gemma)  │
    │ coder)  │    │ coder)  │    │         │
    └─────────┘    └─────────┘    └─────────┘
```

## アーキテクチャデザイン方針

### なぜPull型ポーリングか

- **NAT対応**: Agent HostはControllerへ一方向に接続。家庭内ネットワーク内でもOK
- **セキュリティ**: Ollamaが外部から到達不可
- **スケーラビリティ**: サーバはステートレスなポーリング受け付けのみ
- **簡潔性**: Agentから複数のPC/ネットワークに接続する複雑さがない

### なぜ短命トークンか

- 登録トークンの漏洩時のインパクトを最小化
- 定期的なトークンローテーション機構で定期更新が可能
- 待受トークンをagent_id + pool_idにバインドすることで、トークン単体の権限を限定
- トークン紛失時の範囲限定

## コンポーネント詳細設計

### 1. Agent Host

```
┌─────────────────────────────────────────┐
│         Agent Host Process              │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────────┐    ┌──────────────┐  │
│  │ Config &    │    │ Job Executor │  │
│  │ Auth Mgmt   │──→ │              │  │
│  └─────────────┘    └──────┬───────┘  │
│         │                  │           │
│         │                  ▼           │
│  ┌─────────────┐    ┌──────────────┐  │
│  │ Poller      │    │ Ollama       │  │
│  │ (long-poll) │    │ Connector ──┐│  │
│  └──────┬──────┘    └──────────────┘│  │
│         │                           │  │
│         │ ◄─ localhost:11434 ──────►   │
│         │                 ▲           │
│         │                 │           │
│         │          ┌──────▼────────┐  │
│         │          │   Ollama      │  │
│         │          │   Instance    │  │
│         │          │ (qwen-coder,  │  │
│         │          │  gemma, etc)  │  │
│         │          └───────────────┘  │
│         │                             │
│         ▼ (https)                     │
│   Controller                          │
│   API ─────────────┐                 │
│                    │                 │
└────────────────────│─────────────────┘
                     │
        ┌────────────▼────────────┐
        │ Controller Server       │
        │ - Job Ingestion         │
        │ - State Mgmt            │
        └────────────────────────┘
```

**主要責務**:
- ControllerへのHTTPS接続とポーリング
- 登録・トークン更新ロジック
- ジョブの受け取り、Ollamaへの変換・実行
- 結果のController送信
- リソース監視（CPU、GPU、メモリ）

**実装言語**: Python, Go, Rust（TBD）

**実行環境**: 
- プロセス起動: systemd(Linux), Task Scheduler(Windows), launchd(macOS)
- ローカルストレージ: agent_id, pool_id, 現在のlistener_token

### 2. Controller Server

```
┌─────────────────────────────────────────┐
│      Controller Server (REST API)       │
├─────────────────────────────────────────┤
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ HTTP / gRPC Handler               │ │
│  │ - /agents/* (Agent control)       │ │
│  │ - /jobs/* (Job management)        │ │
│  │ - /v1/* (OpenAI-compatible)       │ │
│  └───────────────────────────────────┘ │
│                   ▲                     │
│                   │                     │
│  ┌────────────────┴────────────────┐   │
│  │                                 │   │
│  ▼                                 ▼   │
│┌─────────────┐        ┌──────────────┐│
││ Auth Service│        │ Job Scheduler││
││ - Token     │        │ - Matching   ││
││   validation│        │ - Dispatch   ││
││ - API key   │        │ - Retry logic││
││   lookup    │        └──────────────┘│
│└─────────────┘                        │
│                                       │
│  ┌──────────────────────────────────┐ │
│  │ State Manager                    │ │
│  │ - Agent pool / agent status      │ │
│  │ - Resource tracking              │ │
│  │ - Job queue                      │ │
│  └──────────────────────────────────┘ │
│                   │                    │
│                   ▼                    │
│  ┌──────────────────────────────────┐ │
│  │ Database Layer (ORM)             │ │
│  └──────────────────────────────────┘ │
│                                       │
└───────────────┬───────────────────────┘
                │
     ┌──────────▼──────────┐
     │ PostgreSQL / SQLite │
     │ - agents            │
     │ - jobs              │
     │ - tokens            │
     │ - audit_logs        │
     │ - api_keys          │
     │ - pools             │
     │ - models            │
     └─────────────────────┘
```

**主要責務**:
- Agent登録・認証・トークン払い出し
- ジョブインジェスト（API Gateway経由）
- ジョブキューへの配布アルゴリズム
- エージェント側ポーリングエンドポイント提供
- 状態管理、ハートビート監視
- 監査ログ記録

**実装言語**: Python (FastAPI/Flask) または Node.js (Express/Fastify)

**実行環境**:
- Docker / Kubernetes推奨
- PostgreSQL or SQLiteデータベース

### 3. API Gateway / Proxy

```
┌─────────────────────────────────────────┐
│      API Gateway (Reverse Proxy)        │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────────────────┐          │
│  │ Request Handler          │          │
│  │ - Route matching         │          │
│  │ - Method validation      │          │
│  └────────────┬─────────────┘          │
│               │                        │
│  ┌────────────▼──────────────┐        │
│  │ Authentication Layer       │        │
│  │ - API Key extraction       │        │
│  │ - Bearer token validation  │        │
│  │ - Scope checking           │        │
│  └────────────┬───────────────┘        │
│               │                        │
│  ┌────────────▼──────────────┐        │
│  │ Rate Limiter               │        │
│  │ - Per-user quota           │        │
│  │ - Per-model throttling     │        │
│  └────────────┬───────────────┘        │
│               │                        │
│  ┌────────────▼──────────────┐        │
│  │ Model Router               │        │
│  │ - Logical model ──→        │        │
│  │   Physical pool matching   │        │
│  │ - Priority assignment      │        │
│  └────────────┬───────────────┘        │
│               │                        │
│  ┌────────────▼──────────────┐        │
│  │ Job Queuer                 │        │
│  │ - Create job record        │        │
│  │ - Enqueue to Controller    │        │
│  │ - Return job ID            │        │
│  └────────────┬───────────────┘        │
│               │                        │
│  ┌────────────▼──────────────┐        │
│  │ Stream / Chunked Response  │        │
│  │ - Server-Sent Events       │        │
│  │ - Trailers (final message) │        │
│  │ - Error handling           │        │
│  └────────────────────────────┘        │
│                                        │
└──────────────────┬─────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
        ▼                     ▼
   Controller Server    (Optional, or
   API Endpoints        co-located)
```

**主要責務**:
- OpenAI互換エンドポイント提供
- Anthropicエンドポイント提供（またはAnthropic互換の中継）
- API keyの検証とスコープチェック
- レート制限実装
- ジョブのController投入
- ストリーミング応答の中継
- リクエスト/レスポンスのロギング

**実装**: Nginx + Lua、HAProxy、APIGateway (AWS/GCP/Azure)、または独自実装（FastAPI等）

### 4. 認証フロー

#### 初回登録フロー

```
Agent Host                         Controller
    │                                 │
    │ POST /agents/register           │
    │ (招待トークン, マシン情報)        ├──→ トークン検証
    │◄────────────────────────────────┤
    │ {                               │
    │   "agent_id": "ag-xxx",         │
    │   "pool_id": "desktop-gpu",     │
    │   "listener_token": "jwt...",   │
    │   "refresh_token": "...",       │
    │   "poll_interval": 30,          │
    │   "expires_in": 3600            │
    │ }                               │
```

#### ポーリング・待受フロー

```
Agent Host                         Controller
    │                                 │
    │ POST /agents/poll               │
    │ Authorization: Bearer jwt...    │
    │ {                               │
    │   "agent_id": "ag-xxx",         │
    │   "status": "idle",             │
    │   "resource": {...}             │
    │ }                               │
    │◄────────────────────────────────┤
    │ 200 OK:                         │
    │ {                               │
    │   "job_id": "job-yyy",          │
    │   "type": "chat-completion",    │
    │   "model": "qwen-coder",        │
    │   "payload": {...}              │
    │ }                               │
    │                                 │
    │ OR 204 No Content (待機)         │
```

#### APIキー認証フロー

```
Client (Python/Node.js)           API Gateway              Controller
    │                                 │                          │
    │ POST /v1/chat/completions       │                          │
    │ Authorization: Bearer sk-...    │                          │
    │─────────────────────────→       │                          │
    │                          Validate API key                  │
    │                          lookup user, scope               │
    │                          ┌────→ Controller DB lookup
    │                          │ ◄────
    │                                 │ Create Job
    │                                 │
    │                     ┌───────────→ Controller
    │                     │            Submit job to queue
    │                     │
    │ ◄──────────────────  Response (with job_id or stream)
```

## データフロー

### chat-completion リクエスト例

```
1. Client Request
   POST /v1/chat/completions
   {
      "model": "qwen-coder",
      "messages": [...]
   }

2. API Gateway
   - Validate API key
   - Check rate limit
   - Create job record
   - Enqueue to Controller

3. Controller -> Job Queue
   - Select matching Agent Pool
   - Find available Agent
   - Assign job to Agent

4. Agent Host Polling
   - Poll: POST /agents/poll
   - Receive: Job description
   - Convert to Ollama API call
      curl http://127.0.0.1:11434/api/chat \
        -d '{"model":"qwen-coder","messages":[...]}'

5. Ollama -> LLM execution
   - Stream response back to Agent Host

6. Agent Host -> Controller
   - POST /jobs/{id}/result
   - Streaming chunks or final result

7. Controller -> API Gateway / Client
   - Stream back to client via SSE or chunked HTTP
```

## トークンライフサイクル

```
┌─────────────────────────────────────────┐
│      Token Types & Lifecycles           │
├─────────────────────────────────────────┤
│                                         │
│ 1. Registration Token (Invitation)      │
│    ├─ Duration: Long (days to weeks)    │
│    ├─ Usage: One-time registration      │
│    ├─ Scope: Any pool                   │
│    └─ Invalidated after use             │
│                                         │
│ 2. Listener Token (Agent Polling)       │
│    ├─ Duration: Short (hours)           │
│    ├─ Usage: Polling, heartbeat         │
│    ├─ Scope: Specific agent_id + pool   │
│    ├─ Renewal: Refresh token exchange   │
│    └─ Rotation: Periodic refresh        │
│                                         │
│ 3. API Key (User/Client Authentication)│
│    ├─ Duration: Long (configurable)    │
│    ├─ Usage: OpenAI/Anthropic API       │
│    ├─ Scope: User scopes (read/write)  │
│    ├─ Revocation: Manual or expiry      │
│    └─ Storage: Hashed in DB             │
│                                         │
│ 4. Refresh Token (Token Renewal)        │
│    ├─ Duration: Medium                  │
│    ├─ Usage: Get new listener_token     │
│    ├─ Scope: Bound to agent_id          │
│    └─ After use: Issue new refresh      │
│                                         │
└─────────────────────────────────────────┘
```

## ネットワーク通信図

```
┌─────────────────────────────────────────────┐
│            Internet / WAN                    │
│                                             │
│  OpenAI SDK Client ◄──► API Gateway         │
│  Claude Code       ◄──►   (HTTPS)           │
│  Custom CLI        ◄──►   (TLS 1.2+)        │
│                          / API keys         │
└────────────────────────┬──────────────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │ Controller Server      │
            │ (Public HTTPS API)     │
            │ - /agents/register     │
            │ - /agents/poll         │
            │ - /v1/...              │
            └────────────┬───────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    TLS/HTTPS mTLS optional
         │               │               │
         ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ Agent 1  │   │ Agent 2  │   │ Agent N  │
    │ (PC-A)   │   │ (PC-B)   │   │ (PC-N)   │
    │          │   │          │   │          │
    │ Ollama   │   │ Ollama   │   │ Ollama   │
    │ :11434   │   │ :11434   │   │ :11434   │
    │ localhost│   │ localhost│   │ localhost│
    └──────────┘   └──────────┘   └──────────┘
       (Private)      (Private)      (Private)
```

## 拡張性ポイント

1. **モデル追加**: Models テーブルに登録し、pool_id でルーティング
2. **新しいジョブタイプ**: Job types enum拡張、Agent Host側のハンドラ追加
3. **レート制限ポリシー**: Gateway側でuserId毎、pool毎に カスタマイズ
4. **複数言語Backend**: Agent Host は Python/Rust/Go + Ollama との組み合わせ自由
5. **監視・アラート**: Prometheus metrics + Grafana、Datadog等と統合可能

