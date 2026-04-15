# Ollama Control Plane - API Specification

## 概要

このドキュメントは、Controller Server、Agent Host、API Gateway の公開APIを仕様化します。

## Part 1: Agent Management API (Controller Server)

Agent Host向けのAPI。TLS必須、mTLS推奨。

### 1.1 Agent Registration

**Endpoint**: `POST /agents/register`

**説明**: Agent Hostが初回登録する。招待トークンをもって参加。

**Authentication**: Invitation Token (Bearer)

**Request**:
```json
{
  "hostname": "desktop-pc-01",
  "capabilities": {
    "models": ["qwen-coder-32b", "qwen-coder-7b"],
    "tools": ["code_execution", "file_read"],
    "max_concurrent_jobs": 2
  },
  "resources": {
    "cpu_cores": 16,
    "gpu_count": 1,
    "gpu_vram_mb": 24000,
    "total_memory_mb": 32000,
    "os": "Linux",
    "arch": "x86_64"
  },
  "pool_preference": "desktop-gpu"
}
```

**Response (201 Created)**:
```json
{
  "agent_id": "ag-550e8400-e29b-41d4-a716-446655440000",
  "pool_id": "desktop-gpu",
  "listener_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "ref_550e8400e29b41d4a716446655440001",
  "expires_in": 3600,
  "refresh_interval": 1800,
  "poll_interval": 30,
  "assigned_models": ["qwen-coder-32b", "qwen-coder-7b"],
  "max_concurrency": 2
}
```

**Error (400 / 401 / 403)**:
```json
{
  "error": "invalid_token | pool_full | unsupported_capability",
  "error_description": "..."
}
```

---

### 1.2 Token Refresh

**Endpoint**: `POST /agents/token/refresh`

**説明**: listener_tokenの有効期限が近い、または期限切れの時に刷新。

**Authentication**: Refresh Token (Bearer)

**Request**:
```json
{
  "agent_id": "ag-550e8400-e29b-41d4-a716-446655440000",
  "refresh_token": "ref_550e8400e29b41d4a716446655440001"
}
```

**Response (200 OK)**:
```json
{
  "listener_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 3600,
  "refresh_token": "ref_550e8400e29b41d4a716446655440002"
}
```

---

### 1.3 Polling (Long-Poll)

**Endpoint**: `POST /agents/poll`

**説明**: Agent HostがControllerにポーリングしてジョブを取得。最大30～60秒待機、ジョブがなければ204を返す。

**Authentication**: Listener Token (Bearer token)

**Request**:
```json
{
  "agent_id": "ag-550e8400-e29b-41d4-a716-446655440000",
  "status": "idle",
  "current_jobs": 0,
  "available_slots": 2,
  "resource_info": {
    "cpu_load": 0.25,
    "gpu_utilization": 0.15,
    "gpu_vram_used_mb": 3000,
    "memory_used_mb": 8000,
    "loaded_models": ["qwen-coder-32b"]
  },
  "last_poll_timestamp": "2026-04-14T10:30:00Z"
}
```

**Response (200 OK - Job Available)**:
```json
{
  "job_id": "job-660f9511-f30c-42cd-b817-557699550111",
  "type": "chat-completion",
  "model": "qwen-coder-32b",
  "timeout_seconds": 300,
  "priority": "normal",
  "payload": {
    "messages": [
      {
        "role": "user",
        "content": "Write a Python function that..."
      }
    ],
    "temperature": 0.7,
    "max_tokens": 2048,
    "stream": true
  }
}
```

**Response (204 No Content - No Job)**:
```
HTTP/1.1 204 No Content
```

**Response (400 / 401)**:
```json
{
  "error": "invalid_agent_id | token_expired",
  "error_description": "..."
}
```

---

### 1.4 Job Result Submission

**Endpoint**: `POST /jobs/{job_id}/result`

**説明**: ジョブ完了時、Agent Hostが結果をControllerに送信。ストリーミングジョブの場合は複数回呼び出し可能。

**Authentication**: Listener Token (Bearer)

**Request (Non-streaming)**:
```json
{
  "agent_id": "ag-550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "execution_time_ms": 1234,
  "usage": {
    "prompt_tokens": 50,
    "completion_tokens": 200,
    "total_tokens": 250
  },
  "result": {
    "message": {
      "role": "assistant",
      "content": "Here's a Python function that..."
    }
  }
}
```

**Request (Streaming - Multiple chunks)**:
```json
{
  "agent_id": "ag-550e8400-e29b-41d4-a716-446655440000",
  "status": "streaming",
  "chunk_index": 0,
  "total_chunks": null,
  "chunk": {
    "delta": {
      "content": "Here's"
    }
  }
}
```

**Response (200 OK)**:
```json
{
  "status": "accepted",
  "message": "Result recorded"
}
```

---

### 1.5 Job Cancellation Notification

**Endpoint**: `POST /jobs/{job_id}/cancel`

**説明**: Controllerがジョブキャンセルを指示（Agentからのポーリング時に返される、または直接呼び出される）

**Authentication**: Listener Token

**Request**:
```json
{
  "agent_id": "ag-550e8400-e29b-41d4-a716-446655440000",
  "reason": "user_requested | timeout | pool_shutdown"
}
```

**Response (200 OK)**:
```json
{
  "acknowledged": true
}
```

---

### 1.6 Heartbeat / Liveness

**Endpoint**: `POST /agents/heartbeat`

**説明**: Agent HostがAlive信号を送信（オプション、ポーリング間隔短い場合は不要）

**Authentication**: Listener Token (Bearer)

**Request**:
```json
{
  "agent_id": "ag-550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-04-14T10:30:00Z",
  "status": "online",
  "resource_snapshot": {
    "cpu_load": 0.2,
    "gpu_utilization": 0.1,
    "gpu_vram_used_mb": 2000,
    "memory_used_mb": 7000
  }
}
```

**Response (200 OK)**:
```json
{
  "status": "acknowledged",
  "server_timestamp": "2026-04-14T10:30:01Z"
}
```

---

## Part 2: Client API (API Gateway / Controller)

OpenAI互換、Anthropic互換エンドポイント。

### 2.1 OpenAI Compatible Endpoints

#### 2.1.1 Chat Completions

**Endpoint**: `POST /v1/chat/completions`

**説明**: OpenAI SDK互換のエンドポイント。`base_url` をこのサーバに向ければ動作。

**Authentication**: API Key (Bearer token)

**Request**:
```bash
curl https://control-plane.local/v1/chat/completions \
  -H "Authorization: Bearer sk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-coder",
    "messages": [
      {"role": "user", "content": "Write a hello world function"}
    ],
    "temperature": 0.7,
    "max_tokens": 2048,
    "stream": true
  }'
```

**Response (200 OK - Non-streaming)**:
```json
{
  "id": "chatcmpl-550e8400",
  "object": "chat.completion",
  "created": 1713083400,
  "model": "qwen-coder",
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 150,
    "total_tokens": 170
  },
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "def hello_world():\n    print('Hello, World!')"
      },
      "finish_reason": "stop"
    }
  ]
}
```

**Response (200 OK - Streaming)**:
```
data: {"id":"chatcmpl-550e8400","object":"chat.completion.chunk","created":1713083400,"model":"qwen-coder","choices":[{"index":0,"delta":{"role":"assistant","content":"def"},"finish_reason":null}]}

data: {"id":"chatcmpl-550e8400","object":"chat.completion.chunk","created":1713083400,"model":"qwen-coder","choices":[{"index":0,"delta":{"content":" hello_world"},"finish_reason":null}]}

...

data: {"id":"chatcmpl-550e8400","object":"chat.completion.chunk","created":1713083400,"model":"qwen-coder","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

---

#### 2.1.2 Models List

**Endpoint**: `GET /v1/models`

**説明**: 利用可能なモデルリストを返す。OpenAI互換。

**Authentication**: API Key

**Response (200 OK)**:
```json
{
  "object": "list",
  "data": [
    {
      "id": "qwen-coder",
      "object": "model",
      "created": 1713000000,
      "owned_by": "control-plane",
      "permission": [
        {
          "id": "modelperm-123",
          "object": "model_permission",
          "created": 1713000000,
          "allow_create_engine": false,
          "is_blocking": false
        }
      ],
      "root": "qwen-coder",
      "parent": null,
      "capabilities": {
        "supports_streaming": true,
        "supports_embeddings": false,
        "context_window": 8192,
        "max_output_tokens": 4096
      }
    },
    {
      "id": "qwen-coder-7b",
      "object": "model",
      "created": 1713000000,
      "owned_by": "control-plane",
      "permission": [...],
      "root": "qwen-coder-7b",
      "parent": null
    }
  ]
}
```

---

#### 2.1.3 Model Details

**Endpoint**: `GET /v1/models/{model_id}`

**説明**: 特定のモデルの詳細情報を返す。

**Authentication**: API Key

**Response (200 OK)**:
```json
{
  "id": "qwen-coder",
  "object": "model",
  "created": 1713000000,
  "owned_by": "control-plane",
  "permission": [...],
  "root": "qwen-coder",
  "parent": null,
  "capabilities": {
    "supports_streaming": true,
    "context_window": 32768,
    "max_output_tokens": 4096,
    "model_family": "qwen",
    "release_date": "2026-01-01",
    "input_cost_per_million_tokens": 0.0,
    "output_cost_per_million_tokens": 0.0
  },
  "available_pools": [
    {
      "pool_id": "desktop-gpu",
      "pool_name": "Desktop GPU Pool",
      "available_agents": 2,
      "average_latency_ms": 150
    }
  ]
}
```

---

### 2.2 Anthropic Compatible Endpoints (Optional)

#### 2.2.1 Messages

**Endpoint**: `POST /v1/messages` (または `/anthropic/v1/messages`)

**説明**: Anthropicクライアント互換。Claude Codeから接続可能。

**Authentication**: API Key (Bearer) or "x-api-key" header

**Request**:
```bash
curl https://control-plane.local/v1/messages \
  -H "x-api-key: sk-..." \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "qwen-coder",
    "max_tokens": 2048,
    "messages": [
      {"role": "user", "content": "Write Python code"}
    ]
  }'
```

**Response (200 OK)**:
```json
{
  "id": "msg-550e8400",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "def hello():\n    print('Hello')"
    }
  ],
  "model": "qwen-coder",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 25,
    "output_tokens": 50
  }
}
```

---

## Part 3: Management API (Controller Admin)

### 3.1 Create Agent Pool

**Endpoint**: `POST /admin/pools`

**Authentication**: Admin API Key

**Request**:
```json
{
  "name": "desktop-gpu",
  "description": "GPU-equipped desktop machines",
  "max_agents": 10,
  "labels": {
    "tier": "high-performance",
    "location": "office"
  }
}
```

**Response (201 Created)**:
```json
{
  "pool_id": "pool-550e8400-e29b-41d4-a716-446655440000",
  "name": "desktop-gpu",
  "description": "GPU-equipped desktop machines",
  "created_at": "2026-04-14T00:00:00Z",
  "agent_count": 0,
  "labels": {
    "tier": "high-performance",
    "location": "office"
  }
}
```

---

### 3.2 List Agents

**Endpoint**: `GET /admin/agents?pool_id={pool_id}`

**Authentication**: Admin API Key

**Response (200 OK)**:
```json
{
  "agents": [
    {
      "agent_id": "ag-550e8400-e29b-41d4-a716-446655440000",
      "hostname": "desktop-pc-01",
      "pool_id": "desktop-gpu",
      "status": "online",
      "last_seen_at": "2026-04-14T10:30:00Z",
      "capabilities": {
        "models": ["qwen-coder-32b"],
        "max_concurrent": 2
      },
      "resource_info": {
        "cpu_cores": 16,
        "gpu_vram_mb": 24000
      },
      "current_jobs": 1,
      "available_slots": 1
    }
  ],
  "total": 1
}
```

---

### 3.3 Create Invitation Token

**Endpoint**: `POST /admin/tokens/invite`

**Authentication**: Admin API Key

**Request**:
```json
{
  "pool_id": "desktop-gpu",
  "expires_in_days": 7,
  "max_uses": 1,
  "labels": {
    "issued_to": "user@example.com"
  }
}
```

**Response (201 Created)**:
```json
{
  "token": "inv_550e8400e29b41d4a716446655440000",
  "pool_id": "desktop-gpu",
  "created_at": "2026-04-14T00:00:00Z",
  "expires_at": "2026-04-21T00:00:00Z",
  "max_uses": 1,
  "remaining_uses": 1
}
```

---

### 3.4 Create API Key

**Endpoint**: `POST /admin/api-keys`

**Authentication**: Admin API Key

**Request**:
```json
{
  "name": "My Application",
  "user_id": "user-xxx",
  "scopes": ["read", "write"],
  "rate_limit": {
    "requests_per_minute": 60
  },
  "expires_in_days": 365
}
```

**Response (201 Created)**:
```json
{
  "api_key_id": "key-550e8400",
  "key": "sk-proj-550e8400e29b41d4a716446655440000",
  "name": "My Application",
  "user_id": "user-xxx",
  "scopes": ["read", "write"],
  "created_at": "2026-04-14T00:00:00Z",
  "expires_at": "2027-04-14T00:00:00Z",
  "rate_limit": {
    "requests_per_minute": 60
  }
}
```

---

## Part 4: Audit & Logging API

### 4.1 Audit Logs

**Endpoint**: `GET /admin/audit-logs?limit=100&offset=0`

**Authentication**: Admin API Key

**Response (200 OK)**:
```json
{
  "logs": [
    {
      "log_id": "log-550e8400",
      "timestamp": "2026-04-14T10:30:00Z",
      "actor_type": "user",
      "actor_id": "user-xxx",
      "action": "job_submitted",
      "resource_type": "job",
      "resource_id": "job-yyy",
      "details": {
        "model": "qwen-coder",
        "pool_id": "desktop-gpu"
      },
      "status": "success",
      "ip_address": "192.168.1.100"
    }
  ],
  "total": 1000,
  "limit": 100,
  "offset": 0
}
```

---

## エラー応答

標準的なHTTPステータスコード + JSON エラー応答：

```json
{
  "error": "invalid_request",
  "error_description": "Missing required field 'model'",
  "error_code": "E001",
  "request_id": "req-550e8400"
}
```

**通常のエラーコード**:
- `400 Bad Request`: リクエスト形式エラー
- `401 Unauthorized`: 認証失敗
- `403 Forbidden`: 権限不足
- `404 Not Found`: リソース未検出
- `409 Conflict`: ステート競合（例: 既に完了したジョブへの結果送信）
- `429 Too Many Requests`: レート制限
- `500 Internal Server Error`: サーバ側エラー
- `503 Service Unavailable`: メンテナンス中やキャパシティ不足

---

## WebSocket対応（将来）

実装の第2段階以降で、Server-Sent Events (SSE) またはWebSocketへ移行して、双方向通信・リアルタイム更新などの対応が可能です。

