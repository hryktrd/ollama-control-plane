# Ollama Control Plane - MVP Scope & Implementation Roadmap

## MVP (Minimum Viable Product) の定義

MVP は「**1台のAgent Host + 1台のController + OpenAI互換APIエンドポイント**」までに限定します。

このスコープであれば、Claude Codeを活用した段階的実装が現実的です。

### MVP 実装範囲

| 要素 | MVP含有 | 説明 |
|-----|--------|------|
| **Agent Host** | ✓ | ローカルOllama接続、基本的なポーリング |
| **Controller** | ✓ | 登録、ポーリング受け口、ジョブ配布（単一Agent） |
| **API Gateway** | ✓ | POST /v1/chat/completions, GET /v1/models |
| **複数Agent対応** | ✗ | Phase 2 |
| **複数Pool対応** | ✗ | Phase 2 |
| **Anthropic互換** | ✗ | Phase 3 |
| **mTLS** | ✗ | Phase 4 |
| **監査ログ詳細版** | △ | 基本ログのみ実装 |
| **Web UI** | ✗ | Phase 3 |

---

## Phase 1: MVP実装 (4-6週間)

### フェーズ1のゴール

```
┌──────────────────┐
│  Agent Host      │
│ (Python)         │
│ - Ollama接続     │
│ - Register       │
│ - Poll & Execute │
└────────┬─────────┘
         │ HTTPS
         ▼
┌──────────────────┐
│  Controller      │
│  (FastAPI)       │
│ - Agent Registry │
│ - Job Queue      │
│ - Basic State    │
└────────┬─────────┘
         │
         ▼
┌──────────────────────┐
│  API Gateway / Proxy │
│  (FastAPI / Nginx)   │
│ - /v1/chat/completions
│ - /v1/models         │
│ - API Key Auth       │
└──────────────────────┘
         │
         ▼
┌──────────────────────┐
│  Client             │
│  (Python/Node.js)   │
│  with OpenAI SDK    │
└──────────────────────┘
```

### Phase 1 の実装タスク

#### 1.1 Agent Host 実装

**ファイル構造**（予定）:
```
agent-host/
├── README.md
├── requirements.txt       # Python dependencies
├── agent_host.py         # Main entry point
├── config/
│   ├── __init__.py
│   └── settings.py       # Configuration management
├── core/
│   ├── __init__.py
│   ├── agent.py          # Agent class
│   ├── poller.py         # Polling logic
│   └── ollama.py         # Ollama API client
├── auth/
│   ├── __init__.py
│   └── token.py          # Token handling
├── job/
│   ├── __init__.py
│   ├── executor.py       # Job execution
│   └── handlers/
│       ├── __init__.py
│       └── chat.py       # Chat completion handler
└── tests/
    ├── __init__.py
    └── test_poller.py
```

**MVP実装で必須**:
- [x] Ollama instance detection & validation
- [x] Local token/config storage
- [x] HTTP HTTPS client with TLS
- [x] Invitation token registration flow
- [x] Listener token JWT handling
- [x] Long-poll implementation with retry
- [x] Chat completion job execution
- [x] Result submission
- [ ] Streaming support （MVP では非流処理版を優先）
- [ ] Multi-model support （単一モデルで試行）

**スタック候補**:
- Python 3.10+
- `aiohttp` または `httpx` (async HTTP)
- `pydantic` (data validation)
- `python-jose` (JWT)
- `requests` (同期フォールバック)

---

#### 1.2 Controller Server 実装

**ファイル構造**:
```
controller/
├── README.md
├── requirements.txt
├── main.py               # FastAPI app entry
├── database/
│   ├── __init__.py
│   ├── models.py         # SQLAlchemy ORM
│   ├── schemas.py        # Pydantic schemas
│   └── crud.py           # CRUD operations
├── api/
│   ├── __init__.py
│   ├── agents.py         # /agents/* routes
│   ├── jobs.py           # /jobs/* routes
│   ├── admin.py          # /admin/* routes
│   └── openai_compat.py  # /v1/* routes
├── core/
│   ├── __init__.py
│   ├── auth.py           # Token validation
│   ├── scheduler.py      # Job scheduling
│   └── manager.py        # Agent state mgmt
├── models/
│   ├── __init__.py
│   ├── agent.py          # Agent entity
│   ├── job.py            # Job entity
│   └── token.py          # Token entity
└── tests/
    ├── __init__.py
    └── test_api.py
```

**MVP実装で必須**:
- [x] FastAPI setup with OpenAPI docs
- [x] SQLite database setup (PostgreSQL への upgrade 対応設計)
- [x] Agent registration endpoint OK
- [x] Listener token generation & validation
- [x] Job polling endpoint
- [x] Job queue (in-memory, Phase 2で書き直し可)
- [x] Basic state management
- [x] Job result reception
- [ ] Rate limiting （MVP では簡易実装や無効）
- [ ] Streaming support
- [ ] Multi-agent scheduling

**スタック**:
- Python 3.10+
- `fastapi`
- `sqlalchemy`
- `pydantic`
- `python-jose` (JWT)
- `passlib` (password hashing, optional for MVP)

---

#### 1.3 API Gateway 実装

**Option A: FastAPI内に組み込む** (MVP推奨)
- Controller の `/api/` ルート内に `/v1/openai-compat` を追加
- 別プロセスではなく、同一サーバで実装

**Option B: Nginx リバースプロキシ** (Phase 2)
- Controller, Agent Proxy を後ろに配置
- ルーティング、認証処理を Nginx Lua で実装

**MVP では Option A** を推奨（実装が簡単、段階的デプロイが可能）

**実装エンドポイント**:
- `POST /v1/chat/completions` → Job作成 + Result待機
- `GET /v1/models` → DB から登録モデル一覧返却

**Authentication**:
- API Key を環境変数またはDB から読み込み
- Bearer token 検証（簡易版）

---

#### 1.4 Database Schema (MVP)

```sql
-- Agent management
CREATE TABLE agents (
  agent_id TEXT PRIMARY KEY,
  pool_id TEXT,
  hostname TEXT UNIQUE NOT NULL,
  status TEXT DEFAULT 'registered',
  capabilities JSONB,
  last_seen_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Job management
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  agent_id TEXT REFERENCES agents(agent_id),
  job_type TEXT NOT NULL,
  model TEXT NOT NULL,
  status TEXT DEFAULT 'pending',
  payload JSONB,
  result JSONB,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  started_at TIMESTAMP,
  completed_at TIMESTAMP
);

-- Token management
CREATE TABLE tokens (
  token_id TEXT PRIMARY KEY,
  token_type TEXT,  -- 'invitation', 'listener', 'refresh', 'api_key'
  agent_id TEXT REFERENCES agents(agent_id),
  token_hash TEXT UNIQUE,
  expires_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  revoked_at TIMESTAMP
);

-- API keys
CREATE TABLE api_keys (
  api_key_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  key_hash TEXT UNIQUE NOT NULL,
  scopes TEXT,  -- JSON array
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP,
  revoked_at TIMESTAMP
);

-- Basic audit
CREATE TABLE audit_logs (
  log_id TEXT PRIMARY KEY,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  event_type TEXT,
  actor_id TEXT,
  resource_type TEXT,
  resource_id TEXT,
  details JSONB
);
```

---

### Phase 1 実装順序

```
Week 1-2: Infrastructure
├─ Database setup (SQLite)
├─ Agent Host skeleton code
├─ Controller FastAPI skeleton
└─ Basic configuration management

Week 2-3: Agent Registration Flow
├─ Invitation token generation & storage
├─ Agent Host registration logic
├─ Listener token generation (JWT)
├─ Token persistence (Agent local config)
└─ Controller token validation

Week 3-4: Polling & Job Execution
├─ Agent Host polling loop
├─ Controller polling endpoint
├─ Basic job queue (in-memory)
├─ Chat completion job handler (Ollama integration)
├─ Ollama API adapter
└─ Result submission flow

Week 4-5: OpenAI API Compatibility
├─ POST /v1/chat/completions endpoint
├─ API key authentication
├─ Job injection in gateway
├─ Response formatting (OpenAI-compatible JSON)
├─ GET /v1/models endpoint
└─ Testing with OpenAI SDK

Week 5-6: Integration & Testing
├─ End-to-end testing (Agent + Controller + Client)
├─ Error handling & retry logic
├─ Docker/container setup
├─ Documentation update
└─ MVP release
```

---

### Phase 1 テスト戦略

```python
# test_agent_registration.py
def test_agent_registration_flow():
    """Agent registration flow のテスト"""
    # 1. Create invitation token
    token = create_invitation_token(pool_id="default")
    
    # 2. Call /agents/register
    response = client.post("/agents/register", 
        headers={"Authorization": f"Bearer {token}"},
        json={...})
    
    assert response.status_code == 201
    assert "agent_id" in response.json()
    assert "listener_token" in response.json()

# test_polling.py
def test_polling_with_job():
    """Polling + job execution のテスト"""
    agent_id = register_test_agent()
    listener_token = get_listener_token(agent_id)
    
    # Enqueue a test job
    job = create_job(agent_id, type="chat-completion")
    
    # Poll and receive job
    response = client.post("/agents/poll",
        headers={"Authorization": f"Bearer {listener_token}"},
        json={"agent_id": agent_id, ...})
    
    assert response.status_code == 200
    assert response.json()["job_id"] == job.id

# test_openai_compat.py
def test_chat_completions():
    """OpenAI compatible API のテスト"""
    import openai
    
    openai.api_key = "test-api-key"
    openai.base_url = "http://localhost:8000/"
    
    response = openai.chat.completions.create(
        model="qwen-coder",
        messages=[{"role": "user", "content": "Hello"}]
    )
    
    assert response.choices[0].message.content is not None
```

---

## Phase 2: 複数Agent・複数Pool対応 (3-4週間)

### Phase 2 のゴール

```
複数エージェント対応
├─ エージェントプール定義
├─ ジョブスケジューリングロジック
├─ リソース考慮（CPU/GPU/VRAM）
└─ エージェント間のロードバランシング

High Priority:
├─ Multi-agent job dispatch
├─ Pool-aware scheduling
├─ Agent health check
├─ Streaming response support
└─ Job priority queue
```

### Phase 2 の主な機能追加

- [ ] Agent Pool テーブル＆管理API
- [ ] Scheduler algorithm (round-robin, resource-aware)
- [ ] Agent heartbeat / health monitoring
- [ ] Job priority (normal, high, critical)
- [ ] Streaming chunk handling
- [ ] Multiple models per pool
- [ ] Load metrics collection

### Phase 2 実装例

```python
# Controller: Job Scheduling
class JobScheduler:
    def schedule_job(self, job):
        """
        ジョブを適切なエージェント・プールへ配布
        """
        # 1. Target pool を決定
        pool = self.get_pool(job.pool_id or "default")
        
        # 2. 条件に合うAgent を探す
        agents = self.find_available_agents(
            pool_id=pool.id,
            model=job.model,
            min_vram=job.required_vram
        )
        
        if not agents:
            job.status = "waiting"  # キューに保留
            return False
        
        # 3. 最適なAgent を選択（リソース/負荷を考慮）
        selected_agent = self.select_best_agent(agents)
        
        # 4. ジョブをQueue に追加
        self.enqueue_job(selected_agent.id, job)
        
        return True

# Agent Host: Streaming support
async def handle_streaming_job(job):
    """
    ストリーミングジョブの場合、逐次送信
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://127.0.0.1:11434/api/chat",
            json=ollama_payload
        ) as response:
            async for line in response.content:
                chunk = json.loads(line)
                
                # 逐次送信
                await submit_streaming_chunk(
                    job_id=job.id,
                    chunk=chunk
                )
```

---

## Phase 3: Claude Code 統合 & Anthropic互換API (3-4週間)

### Phase 3 のゴール

```
Claude Code 対応
├─ Anthropic compatible endpoint
├─ Model aliasing (論理名 → 実名)
└─ Claude Code IDE plugin対応

Advanced Features:
├─ Web management UI
├─ Audit logging (詳細版)
├─ Configuration dashboard
└─ Real-time metrics
```

### Phase 3 の主な機能追加

- [ ] POST /v1/messages endpoint (Anthropic-compatible)
- [ ] Model aliasing & routing layer
- [ ] Web UI (React / Vue.js)
  - Agent 一覧・監視
  - ジョブ履歴
  - API KEY 管理
  - 監査ログビュー
- [ ] Detailed audit logging
- [ ] Prometheus metrics export
- [ ] Webhook notifications

---

## Phase 4: セキュリティ・運用機能 (2-3週間)

### Phase 4 のゴール

```
本番対応
├─ mTLS for Agent ↔ Controller
├─ Advanced rate limiting
├─ Permission & role management
└─ Deployment automation
```

### Phase 4 の主な機能追加

- [ ] mTLS certificate generation & validation
- [ ] Redis-backed rate limiting
- [ ] Role-based access control (RBAC)
- [ ] Permission scoping
- [ ] Helm chart / Docker compose
- [ ] Monitoring & alerting (Prometheus/Grafana)
- [ ] Backup & disaster recovery
- [ ] Multi-tenancy support (if needed)

---

## 実装費用推定 (Claude Code を活用)

| Phase | 期間 | 主要作業 | Claude詐取 |
|-------|------|--------|----------|
| **MVP (Phase 1)** | 4-6週間 | Agent + Controller + API | 70% |
| **Phase 2** | 3-4週間 | スケーリング | 60% |
| **Phase 3** | 3-4週間 | Claude統合・WebUI | 50% |
| **Phase 4** | 2-3週間 | セキュリティ・運用 | 40% |
| **Subtotal** | 12-17週間 | | 55% (avg) |

**Notes**:
- 各Phaseで Claude Code を**段階的に活用**、初期実装は自分で仕上げ確認
- テストコード・ドキュメントはいずれも重要。Claude に任せすぎずレビュー推奨
- Phaseの切り替え時に、前Phaseの技術債を軽く片付ける期間を設ける

---

## MVP 後の確認事項・今後の展開

### ✓ MVP完了後の検証ポイント

1. **パフォーマンス**
   - Agent 1台・Control 1台で、1日あたり何requests?
   - レイテンシ（登録～ジョブ配信～実行結果受信）

2. **安定性**
   - 長時間稼働時の リソースリーク
   - トークン更新が正常に行われるか

3. **スケール可能性**
   - 複数Agent追加時の スケジューリング品質
   - DB パフォーマンス（インデックス確認）

### 🔄 Phase 2 へのスムーズな移行

- Phase 1 では意図的に **単一Agent対応** に絞った
- Phase 2 では、DB query を最適化、Scheduler アルゴリズムを導入
- 既存 API は backward-compatible に保つ

### 💾 データマイグレーション戦略

- Phase 1: SQLite で十分
- Phase 2-3: PostgreSQL への migration (simple)
- Alembic / Alembic で schema evolution を management

---

## MVP 実装チェックリスト

### Agent Host MVP

- [ ] Installation guide
- [ ] Configuration (环境变数、config file)
- [ ] Ollama connectivity test
- [ ] Registration flow (invitation token → listener token)
- [ ] Polling loop
- [ ] Chat completion handler
- [ ] Error handling & retry
- [ ] Systemd / Task Scheduler integration
- [ ] Log output
- [ ] Unit tests (>80% coverage)
- [ ] Docstring / README

### Controller MVP

- [ ] Database initialization
- [ ] Agent registration API
- [ ] Token management (generation, validation, refresh)
- [ ] Polling endpoint
- [ ] Job queue (basic)
- [ ] Result reception
- [ ] OpenAI compatible endpoints
- [ ] API key authentication
- [ ] Error responses (proper HTTP status codes)
- [ ] Integration tests
- [ ] Docker image
- [ ] README / API documentation

### Client Integration

- [ ] OpenAI Python SDK compatibility test
- [ ] OpenAI Node.js SDK compatibility test (bonus)
- [ ] Custom CLI tool example (optional)
- [ ] Example notebook (Claude Code可以试)

---

## デプロイ・実行方法（MVP予定）

```bash
# 1. Controller Setup
cd controller
export DATABASE_URL="sqlite:///./test.db"
export CONTROLLER_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
export JWT_ALGORITHM="HS256"

pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

# 2. Invite Agent
curl -X POST http://localhost:8000/admin/tokens/invite \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-key>" \
  -d '{"pool_id": "default", "expires_in_days": 7}'

# 3. Agent Setup
cd ../agent-host
export INVITATION_TOKEN="inv_xxxx"
export CONTROLLER_URL="http://localhost:8000"
export OLLAMA_URL="http://127.0.0.1:11434"

pip install -r requirements.txt
python agent_host.py

# 4. Client Test
python -c "
import openai
openai.api_key = 'sk-test'
openai.base_url = 'http://localhost:8000/'
response = openai.chat.completions.create(
  model='qwen-coder',
  messages=[{'role': 'user', 'content': 'Hello'}]
)
print(response.choices[0].message.content)
"
```

---

## Next Steps (今すぐ)

1. **本ドキュメントの確認** ✓
2. **プロジェクトリポジトリのセットアップ** (完了)
3. **Claude Code でPhase 1の先行実装検討** 
   - Agent Host skeleton
   - Controller skeleton
   - 基本的な登録フロー
4. **段階的なテスト・フィードバックループ**

