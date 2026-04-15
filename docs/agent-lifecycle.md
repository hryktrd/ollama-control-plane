# Ollama Control Plane - Agent Lifecycle

## Agent のステートマシン

```
                  ┌──────────────────┐
                  │   UNREGISTERED   │
                  │ (初期状態)        │
                  └────────┬─────────┘
                           │
                           │ POST /agents/register
                           │ (招待トークン で認証)
                           ▼
                  ┌──────────────────┐
                  │  REGISTRATION    │
                  │ (登録処理中)       │
                  └────────┬─────────┘
                           │
                    Success│ Failure
                           │ ▼
         ┌─────────────────┴──────────────┐
         │                                │
         ▼                                ▼
┌──────────────────┐         ┌──────────────────┐
│  REGISTERED      │         │  REGISTRATION    │
│ (登録成功)        │         │  FAILED          │
└────────┬─────────┘         │ (登録失敗)        │
         │                   └────────┬─────────┘
         │ listener_token               │
         │ を取得                      │ Retry check
         │                             │
         ▼                             │
┌──────────────────┐                  │
│    READY         │──────────────────┘
│ (ポーリング待機) │
└────┬──────┬─────┘
     │      │
     │      └─────────────► EXPIRED
     │        listener_token  (トークン期限切れ)
     │        の有効期限切れ       (→ Token Refresh)
     │
     │ POST /agents/poll
     │ (ジョブ取得)
     │
     ▼
┌──────────────────┐
│     POLLING      │
│ (ポーリング中)   │
└────────┬─────────┘
         │
    Job├─ No job
    available     204 No Content
    ├─ Job available
    │     ▼
    │ ┌──────────────────┐
    │ │  JOB_RECEIVED    │
    │ │ (ジョブ受信)      │
    └─→ └────────┬─────────┘
         │
         │ Job execution
         ▼
┌──────────────────┐
│   EXECUTING      │
│ (実行中)         │
└────┬──────┬─────┘
     │      │
     │      └─────────────► TIMEOUT
     │        (実行タイムアウト)
     │
     │ Execution completed
     │
     ▼
┌──────────────────────┐
│   RESULT_SUBMITTING  │
│ (結果送信中)         │
└────────┬─────────────┘
         │
     ┌───┴────────────────┐
     │                    │
    Success│              │Failure│
     │                    │
     ▼                    ▼
┌──────────┐      ┌──────────────────┐
│  IDLE    │      │ RESULT_FAILED    │
│(待機中)  │      │ (結果送信失敗)    │
└────┬─────┘      └────────┬─────────┘
     │                     │
     │                 Retry│
     │                     │
     │◄────────────────────┘
     │
     │ Heartbeat / Next poll
     ▼
      READY  (← ポーリング戻る)


Special States:
─────────────────

┌──────────────────┐
│   OFFLINE        │ Agent HostがControllerに接続できない状態
│ (オフライン)     │ last_seen_at から30秒以上応答なし
└─────────────────┘
     │
     └─► Agent再起動 → REGISTERED (自動復帰)


┌──────────────────┐
│   ERROR          │ ジョブ実行エラーやポーリング失敗
│ (エラー状態)      │  
└────────┬─────────┘
         │
         └─► Manual intervention or auto-retry
             (設定によって異なる)


┌──────────────────┐
│   DEREGISTERED   │ Admin が /admin/agents/{id}/deregister
│ (登録解除)        │ または定期メンテナンス等で削除
└─────────────────┘
     │
     └─► 新規登録が必要
```

---

## Agent ライフサイクル詳細

### Phase 1: 初期化・登録

#### 1.1 環境セットアップ

Agent Hostマシン上で実行される初期化処理：

```bash
# セットアップスクリプト実行
$ curl https://control-plane.local/bootstrap.sh | bash

# または Docker コンテナ起動時に環境変数注入
docker run \
  -e INVITATION_TOKEN="inv_xxxxx" \
  -e CONTROLLER_URL="https://control-plane.local" \
  -e POLL_INTERVAL=30 \
  ollama-agent:latest
```

**チェックボックス**:
- [ ] Ollamaプロセスランニング確認 (port 11434)
- [ ] ネットワーク接続確認
- [ ] 招待トークン取得

#### 1.2 /agents/register 呼び出し

Agent HostプロセスがController登録を試行：

```python
def register_agent():
    response = requests.post(
        f"{CONTROLLER_URL}/agents/register",
        headers={
            "Authorization": f"Bearer {INVITATION_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "hostname": "desktop-pc-01",
            "capabilities": {
                "models": ["qwen-coder-32b"],
                "tools": ["code_execution"],
                "max_concurrent_jobs": 2
            },
            "resources": {
                "cpu_cores": 16,
                "gpu_count": 1,
                "gpu_vram_mb": 24000,
                "total_memory_mb": 32000,
                "os": "Linux",
                "arch": "x86_64"
            }
        },
        timeout=10
    )
    
    if response.status_code == 201:
        data = response.json()
        agent_id = data["agent_id"]
        listener_token = data["listener_token"]
        poll_interval = data["poll_interval"]
        
        # ローカル保存
        save_config({
            "agent_id": agent_id,
            "listener_token": listener_token,
            "poll_interval": poll_interval,
            "registered_at": datetime.utcnow().isoformat()
        })
        
        return True
    else:
        logger.error(f"Registration failed: {response.text}")
        return False
```

**エラーハンドリング**:
- `400 Bad Request`: リクエスト形式エラー (マシン情報不足)
- `401 Unauthorized`: 招待トークン不正/期限切れ
- `403 Forbidden`: Pool満杯
- `409 Conflict`: 既に登録済みhostname
- `500 Server Error`: Controllerサイド異常 (再試行待機)

#### 1.3 トークン・設定ローカル保存

Agent Hostのローカルストレージに以下を保存：

```
~/.ollama-control-plane/
├── config.json
│   {
│     "agent_id": "ag-550e8400-e29b-41d4-a716-446655440000",
│     "listener_token": "eyJhbGci...",
│     "poll_interval": 30,
│     "registered_at": "2026-04-14T10:00:00Z"
│   }
├── .listener_token (シンボリックリンク or git-ignored)
└── registration.log
```

**セキュリティ**:
- `config.json` は mode 0600 (read only for owner)
- `.listener_token` は環境変数からメモリ読み込み推奨（実装によってはファイルOK）

---

### Phase 2: ポーリング・待機

#### 2.1 ポーリングループ

登録後、Agent Hostはループで以下を繰り返す：

```python
async def polling_loop():
    while True:
        try:
            response = await poll_for_jobs()
            
            if response.status_code == 200:
                job = response.json()
                await execute_job(job)
            elif response.status_code == 204:
                # No job, wait until next poll
                logger.debug("No job available")
            elif response.status_code == 401:
                # Token expired
                await refresh_listener_token()
            else:
                logger.error(f"Poll error: {response.status_code}")
                await exponential_backoff()
        
        except Exception as e:
            logger.error(f"Polling loop error: {e}")
            await exponential_backoff()
        
        await asyncio.sleep(POLL_INTERVAL)


async def poll_for_jobs():
    payload = {
        "agent_id": agent_id,
        "status": get_current_status(),
        "current_jobs": count_running_jobs(),
        "available_slots": max_concurrency - count_running_jobs(),
        "resource_info": {
            "cpu_load": get_cpu_load(),
            "gpu_utilization": get_gpu_util(),
            "gpu_vram_used_mb": get_gpu_vram(),
            "memory_used_mb": get_memory_used(),
            "loaded_models": get_loaded_models()
        }
    }
    
    response = requests.post(
        f"{CONTROLLER_URL}/agents/poll",
        headers={"Authorization": f"Bearer {listener_token}"},
        json=payload,
        timeout=120  # Long poll timeout
    )
    
    return response
```

**ポーリング戦略**:
- **Long-poll**: Controller側で最大60秒待機してジョブがあれば即座に返す
- **Fallback**: 60秒でタイムアウト → Client側ですぐ再ポーリング
- **指数バックオフ**: エラー時は 1秒 → 2秒 → 4秒 → 最大60秒

#### 2.2 リソース監視

ポーリング時にリソース情報を定期的に更新：

```python
def get_current_status():
    cpu_load = psutil.cpu_percent(interval=1) / 100
    
    if psutil.virtual_memory().percent > 80:
        status = "high_memory"
    elif count_running_jobs() >= max_concurrency:
        status = "busy"
    else:
        status = "idle"
    
    return status
```

**ステータス値**:
- `idle`: 文字通りアイドル、ジョブ受け付け可能
- `busy`: 最大稼働中
- `high_memory`: メモリ逼迫、新規ジョブ避ける
- `online`: Active polling (内部状態)
- `offline`: No response from Controller

---

### Phase 3: ジョブ実行

#### 3.1 Job受信

```python
async def execute_job(job: dict):
    job_id = job["job_id"]
    job_type = job["type"]
    model = job["model"]
    payload = job["payload"]
    timeout_seconds = job.get("timeout_seconds", 300)
    
    logger.info(f"Executing job {job_id} with model {model}")
    
    try:
        if job_type == "chat-completion":
            result = await execute_chat_completion(model, payload, timeout_seconds)
        elif job_type == "embedding":
            result = await execute_embedding(model, payload, timeout_seconds)
        elif job_type == "code-task":
            result = await execute_code_task(model, payload, timeout_seconds)
        else:
            raise ValueError(f"Unknown job type: {job_type}")
        
        # 結果送信
        await submit_job_result(job_id, "completed", result)
    
    except TimeoutError:
        await submit_job_result(job_id, "timeout", {"error": "Execution timeout"})
    except Exception as e:
        await submit_job_result(job_id, "error", {"error": str(e)})
```

#### 3.2 Ollama API 呼び出し

```python
async def execute_chat_completion(model: str, payload: dict, timeout: int):
    """
    ローカルOllama APIへの変換・実行
    """
    messages = payload.get("messages", [])
    temperature = payload.get("temperature", 0.7)
    max_tokens = payload.get("max_tokens", 2048)
    stream = payload.get("stream", False)
    
    ollama_payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens
        }
    }
    
    start_time = time.time()
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://127.0.0.1:11434/api/chat",
                json=ollama_payload,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status != 200:
                    error = await response.text()
                    raise Exception(f"Ollama API error: {error}")
                
                if stream:
                    chunks = []
                    async for line in response.content:
                        chunk = json.loads(line)
                        chunks.append(chunk)
                        # ストリーミングの場合、逐次送信も可能
                    
                    return {
                        "message": chunks[-1].get("message", {}),
                        "streaming": True
                    }
                else:
                    data = await response.json()
                    return data
    
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        raise TimeoutError(f"Ollama API timeout after {elapsed}s")
```

#### 3.3 ストリーミング処理

Streaming対応ジョブの場合：

```python
async def submit_job_result_streaming(job_id: str, chunk: dict):
    """
    ストリーミング中間結果を逐次送信
    """
    payload = {
        "agent_id": agent_id,
        "status": "streaming",
        "chunk": chunk
    }
    
    response = requests.post(
        f"{CONTROLLER_URL}/jobs/{job_id}/result",
        headers={"Authorization": f"Bearer {listener_token}"},
        json=payload
    )
    
    if response.status_code != 200:
        logger.warning(f"Failed to submit streaming chunk: {response.text}")
```

Controller側ではこれをClient（OpenAI SDK）へServer-Sent Events (SSE) で中継します。

---

### Phase 4: 結果送信・完了

#### 4.1 結果送信

```python
async def submit_job_result(job_id: str, status: str, result: Any):
    """
    ジョブ実行結果をControllerに送信
    status: "completed", "error", "timeout"
    """
    payload = {
        "agent_id": agent_id,
        "status": status,
        "execution_time_ms": int((time.time() - job_start_time) * 1000),
        "usage": extract_usage_info(result),
        "result": result
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{CONTROLLER_URL}/jobs/{job_id}/result",
                headers={"Authorization": f"Bearer {listener_token}"},
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Job {job_id} result submitted successfully")
                return True
            else:
                logger.warning(f"Result submission failed: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Result submission error (attempt {attempt+1}): {e}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    logger.error(f"Failed to submit result for job {job_id} after {max_retries} attempts")
    return False
```

**Retry戦略**:
- 最大3回まで再試行
- 最初の失敗: 1秒待機
- 2番目の失敗: 2秒待機
- 3番目の失敗: 4秒待機後、最終的にログ記録

#### 4.2 次のポーリングへ

結果送信完了後、Agent Hostは READY 状態に戻り、次のポーリングサイクルへ進む。

---

### Phase 5: トークン更新

#### 5.1 Listener Token 有効期限切れ検知

```python
def should_refresh_token():
    token_payload = jwt.decode(listener_token, options={"verify_signature": False})
    expires_at = datetime.utcfromtimestamp(token_payload["exp"])
    now = datetime.utcnow()
    
    time_to_expiry = (expires_at - now).total_seconds()
    
    # 有効期限30分前にリフレッシュ
    return time_to_expiry < 1800  # 30 minutes
```

#### 5.2 Token Refresh リクエスト

```python
async def refresh_listener_token():
    """
    listener_token を更新
    """
    payload = {
        "agent_id": agent_id,
        "refresh_token": refresh_token
    }
    
    response = requests.post(
        f"{CONTROLLER_URL}/agents/token/refresh",
        json=payload,
        timeout=10
    )
    
    if response.status_code == 200:
        data = response.json()
        new_listener_token = data["listener_token"]
        new_refresh_token = data.get("refresh_token", refresh_token)
        
        # 新しいトークンでローカル設定を更新
        update_local_token(new_listener_token, new_refresh_token)
        logger.info("Listener token refreshed successfully")
        
        return True
    else:
        logger.error(f"Token refresh failed: {response.text}")
        # リトライロジックまたは再登録へ
        return False
```

---

### Phase 6: オフライン・再接続

#### 6.1 接続喪失検知

```python
async def detect_offline():
    """
    Controller との通信が60秒以上途絶えたらOFFLINEと判定
    """
    last_successful_poll = time.time()
    
    while True:
        try:
            await poll_for_jobs()
            last_successful_poll = time.time()
            status = "online"
        
        except Exception as e:
            elapsed = time.time() - last_successful_poll
            if elapsed > 60:
                status = "offline"
                logger.warning("Agent offline - cannot reach Controller")
        
        await asyncio.sleep(POLL_INTERVAL)
```

#### 6.2 再接続処理

```python
async def handle_offline_mode():
    """
    OFFLINE状態でキューイングされたジョブをメモリに保持
    Controller 復帰時に同期
    """
    pending_jobs = []
    
    while is_offline:
        try:
            await poll_for_jobs()
            is_offline = False
            
            # 保留中ジョブを再提出
            for job in pending_jobs:
                logger.info(f"Resuming job {job['job_id']}")
        
        except:
            # Memory queue 保持（DEV/MVP: 永続化は Phase 2)
            logger.debug("Still offline, retrying in 10s")
            await asyncio.sleep(10)
```

---

### Phase 7: 登録解除・シャットダウン

#### 7.1 Graceful Shutdown

```python
async def graceful_shutdown():
    """
    Agent Hostプロセス終了時の処理
    """
    logger.info("Shutting down agent gracefully...")
    
    # 1. 新規ジョブ受け付け停止
    accepting_jobs = False
    
    # 2. 実行中ジョブの完了待機（タイムアウト付き）
    timeout_at = time.time() + 30  # 30秒待機
    while count_running_jobs() > 0 and time.time() < timeout_at:
        await asyncio.sleep(1)
    
    # 3. 強制終了対象のジョブをキャンセル
    for job in get_running_jobs():
        if time.time() >= timeout_at:
            try:
                job.process.terminate()
            except:
                pass
    
    # 4. ポーリングループ終了
    stop_polling_loop()
    
    # 5. OFFLINE状態を報告（次回起動時に復帰）
    logger.info("Agent shutdown complete")
```

#### 7.2 Admin による登録解除

```bash
# Admin APIで登録解除
curl -X DELETE https://control-plane.local/admin/agents/ag-550e8400 \
  -H "Authorization: Bearer <admin-api-key>"
```

---

## 状態遷移表

| From | To | Event | Condition |
|------|-----|-------|-----------|
| UNREGISTERED | REGISTRATION | POST /agents/register送信 | Always |
| REGISTRATION | REGISTERED | 成功 | response.status_code == 201 |
| REGISTRATION | REGISTRATION_FAILED | 失敗 | response.status_code != 201 |
| REGISTRATION_FAILED | REGISTRATION | Retry click or auto-retry | exponential backoff |
| REGISTERED | READY | Config保存完了 | listener_token有効 |
| READY | EXPIRED | listener_token有効期限切れ | time > exp |
| EXPIRED | READY | Token Refresh成功 | refresh_token有効 |
| READY | POLLING | POST /agents/poll送信 | Always |
| POLLING | READY | No job (204) | Always |
| POLLING | JOB_RECEIVED | Job available (200) | Always |
| JOB_RECEIVED | EXECUTING | ジョブ実行開始 | Always |
| EXECUTING | RESULT_SUBMITTING | 実行完了 | Always |
| EXECUTING | TIMEOUT | タイムアウト発生 | elapsed > timeout_seconds |
| RESULT_SUBMITTING | IDLE | 結果送信成功 | status == 200 |
| RESULT_SUBMITTING | RESULT_FAILED | 結果送信失敗 | status != 200 |
| RESULT_FAILED | RESULT_SUBMITTING | Retry | max_retries未達 |
| IDLE | READY | Next poll cycle | Always |
| Any | OFFLINE | No response > 60s | Controller unreachable |
| OFFLINE | REGISTERED | Controller再接続 | Connection restored |
| Any | DEREGISTERED | Admin delete / maintenance | Manual or scheduled |

