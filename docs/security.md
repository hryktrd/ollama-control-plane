# Ollama Control Plane - Security Design

## セキュリティ要件

Ollama Control Planeは以下のセキュリティ要件を満たす必要があります。

### 1. 機密性 (Confidentiality)
- 通信の暗号化
- 認証情報の安全な保管
- ジョブペイロードの秘匿性

### 2. 完全性 (Integrity)
- メッセージ改ざん検知
- トークン署名検証
- 監査ログの改ざん防止

### 3. 可用性 (Availability)
- レート制限によるDoS対策
- リソースの公平な配分
- フェイルセーフなシャットダウン

### 4. 認可 (Authorization)
- スコープに基づくアクセス制御
- リソースレベルのアクセス制限
- API keyの最小権限原則

---

## 1. 通信セキュリティ

### 1.1 TLS/SSL

**要件**: すべてのネットワーク通信はTLS 1.2以上を使用すること。

**実装ガイドライン**:
```
# Controller Server
- 証明書: Let's Encrypt (自動更新推奨) または 企業CA
- 秘密鍵: 環境変数、Secret Manager から読み込み
- TLS 1.3 推奨、最低 TLS 1.2
- 強力な暗号スイート: AES-256-GCM, ChaCha20
- HSTS を有効化（max-age=31536000）
  Header: Strict-Transport-Security: max-age=31536000; includeSubDomains
```

**検証**:
```bash
# TLSバージョンと暗号スイート確認
openssl s_client -connect control-plane.local:443

# 弱い暗号スイートを避ける
# SSLv3、TLS 1.0/1.1 は使用禁止
```

### 1.2 mTLS (Mutual TLS - Agent ↔ Controller)

**要件**: Agent HostとController間はmTLSで通信すること（推奨）。

**実装**:
```
Agent Host
├─ CA証明書 (control-plane-ca.crt)
├─ クライアント証明書 (agent-{agent_id}.crt)
└─ クライアント秘密鍵 (agent-{agent_id}.key)

Controller Server
├─ サーバ証明書 (control-plane.crt)
├─ サーバ秘密鍵 (control-plane.key)
├─ CA証明書 (agent-ca.crt)  # Agentクライアント証明書検証用
└─ CRL / OCSP スタプリング対応
```

**登録フロー**:
```
1. Agent Host: 招待トークンで /agents/register を叩く (HTTPS TLS 1.2+)
2. Controller: Agent を登録、クライアント証明書を発行
3. Agent Host: 証明書をローカル保存
4. 次回以降: mTLS で通信
```

---

## 2. 認証設計

### 2.1 トークン体系

#### 2.1.1 登録トークン (Invitation Token)

**目的**: Agent初回登録のみに使用。

**生成**:
```python
# Controller生成時
import secrets
import hmac
import hashlib
from datetime import datetime, timedelta

def generate_invitation_token():
    raw_token = secrets.token_urlsafe(32)  # 256-bit
    hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    # DB保存: (token_hash, expires_at, pool_id, max_uses)
    return raw_token  # ユーザーに配布
```

**検証**:
```python
def validate_invitation_token(raw_token):
    hash = hashlib.sha256(raw_token.encode()).hexdigest()
    record = db.query("SELECT * FROM invitation_tokens WHERE token_hash = ?", [hash])
    
    if not record or record.expires_at < datetime.utcnow() or record.uses >= record.max_uses:
        raise InvalidTokenError()
    
    # トークン消費
    db.execute("UPDATE invitation_tokens SET uses = uses + 1 WHERE token_hash = ?", [hash])
    return record.pool_id
```

**特性**:
- 一回限りまたは限定使用量
- 初回登録後は即座に无効化
- DB内ではハッシュ化して保存
- 7日程度の有効期限

---

#### 2.1.2 待受トークン (Listener Token)

**目的**: Agent Hostがポーリングする際の認証。

**実装**: JWT (JSON Web Token)

```python
from jose import jwt
from datetime import datetime, timedelta
import os

SECRET_KEY = os.environ["CONTROLLER_SECRET"]

def generate_listener_token(agent_id: str, pool_id: str, ttl_hours: int = 1):
    now = datetime.utcnow()
    expires_at = now + timedelta(hours=ttl_hours)
    
    payload = {
        "sub": agent_id,
        "pool_id": pool_id,
        "type": "listener",
        "iat": now,
        "exp": expires_at,
        "iss": "control-plane"
    }
    
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return token


def validate_listener_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "listener":
            raise ValueError("Invalid token type")
        return payload
    except JWTError:
        raise InvalidTokenError()
```

**特性**:
- 短命（1～2時間の有効期限）
- agent_id + pool_idにバインド（トークン単体では他のagentで使用不可）
- JWTで署名検証可能（秘密鍵不要）
- 定期的なリフレッシュで更新
- クレーム内に権限情報を包含可能

**定期更新フロー**:
```
Agent Host:
1. listener_tokenが期限の30分前 → POST /agents/token/refresh
2. Refresh Token で新しい listener_tokenを取得
3. 古いリスナーtokenを破棄
4. 新しいtokenで poll を続行
```

---

#### 2.1.3 APIキー (User Authentication)

**目的**: OpenAI互換API、Anthropic互換API、Admin APIのクライアント認証。

**生成**:
```python
import secrets

def generate_api_key(user_id: str, name: str, scopes: list):
    # sk-proj-{random_part}
    prefix = "sk-proj-"
    random_part = secrets.token_urlsafe(48)  # 384-bit
    key = prefix + random_part
    
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    
    db.insert("api_keys", {
        "user_id": user_id,
        "key_hash": key_hash,
        "name": name,
        "scopes": json.dumps(scopes),
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=365),
        "rate_limit": 60,  # requests per minute
        "last_used_at": None
    })
    
    return key  # ユーザーに一度だけ表示
```

**検証**:
```python
def validate_api_key(key: str):
    prefix, _, rest = key.partition("-")
    if prefix != "sk" and prefix != "sk-proj":
        raise InvalidKeyError()
    
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    record = db.query("SELECT * FROM api_keys WHERE key_hash = ?", [key_hash])
    
    if not record or record.expires_at < datetime.utcnow():
        raise InvalidKeyError()
    
    # Rate limiting check
    if is_rate_limited(record.user_id):
        raise RateLimitError()
    
    # Update last_used
    db.execute("UPDATE api_keys SET last_used_at = ? WHERE key_hash = ?", 
               [datetime.utcnow(), key_hash])
    
    return record
```

**特性**:
- DB内ではハッシュ化して保存（復元不可）
- 有効期限あり（デフォルト1年）
- 定期的なローテーション推奨（90日ごと）
- スコープ管理（どのAPIを使えるか）
- レート制限とのbinding
- 使用履歴の記録

---

### 2.2 認証フロー詳細

#### 登録フロー
```
1. Admin: 招待トークン生成
   POST /admin/tokens/invite
     Body: pool_id, expires_in_days, max_uses
     → Response: inv_...

2. User: Agent Hostのセットアップ
   Agent実行時に環境変数: INVITATION_TOKEN=inv_...

3. Agent: Controller登録
   POST /agents/register
     Header: Authorization: Bearer inv_...
     Body: hostname, capability, resources
     → Response: agent_id, listener_token, expires_in

4. Agent: listener_token ローカル保存
   ~/.ollama-control-plane/listener.token
   ~/.ollama-control-plane/agent.id

5. 以後: listener_token で認証
   POST /agents/poll
     Header: Authorization: Bearer <JWT from listener_token>
```

#### APIキー認証フロー
```
1. User/Admin: APIキー生成
   POST /admin/api-keys
     Body: name, scopes, rate_limit, expires_in_days
     → Response: sk-proj-... (一度だけ表示)

2. User: APIキーをアプリに設定
   import openai
   openai.api_key = "sk-proj-..."
   openai.base_url = "https://control-plane.local/"

3. Client Library: リクエスト送信
   POST /v1/chat/completions
     Header: Authorization: Bearer sk-proj-...
     Body: messages, model, ...

4. API Gateway: キー検証
   - キーハッシュをDB lookup
   - スコープ確認
   - レート制限チェック
   - ジョブ投入

5. ロギング: 監査ログに記録
```

---

## 3. 暗号化

### 3.1 保存中の暗号化 (Data at Rest)

**APIキー・トークン**:
```
- DB内: ハッシュ化（不可逆）
- メモリ内: 通常のメモリ（プロセス終了で削除）
- ディスク: DBの暗号化機能を使用
  PostgreSQL: pgcrypto拡張、ENCRYPTED COLUMNs
  SQLite: SQLCipher
```

**センシティブなジョブペイロード**:
```
- DB内: 必要に応じてAES-256-GCMで暗号化
- 論理的には、ジョブペイロードは一時的なため、
  通常は暗号化不要（TLSで十分）
```

**秘密鍵**:
```
- 環境変数で注入（CI/CDパイプライン）
- HashiCorp Vault, AWS Secrets Manager等の
  外部Secret Managerを推奨
- ディスク上には平文で置かない
```

### 3.2 転送中の暗号化 (Data in Transit)

- TLS 1.2+で全通信を暗号化
- 強力な暗号スイート（AES-256-GCM）
- Forward Secrecy対応（ECDHE）

---

## 4. 認可と権限管理

### 4.1 ロールベースアクセス制御 (RBAC)

```
┌─────────────┬──────────────────────┬──────────────────┐
│ Role        │ Agent API            │ User API         │
├─────────────┼──────────────────────┼──────────────────┤
│ Admin       │ ✓ Full access        │ ✓ Full access    │
│ Agent Host  │ ✓ Register, Poll     │ ✗                │
│ User        │ ✗                    │ ✓ ChatComplete   │
│ Service     │ Limited (per pool)   │ Limited (embed)  │
└─────────────┴──────────────────────┴──────────────────┘
```

### 4.2 スコープ管理

```json
{
  "api_key": "sk-proj-xxx",
  "scopes": [
    "chat.complete",    // OpenAI /v1/chat/completions
    "models.list",      // GET /v1/models
    "embeddings",       // Future: embeddings API
    "admin"             // Admin endpoints (restricted)
  ]
}
```

**スコープ検証**:
```python
def check_scope(api_key, required_scope):
    if required_scope not in api_key.scopes:
        raise InsufficientScopeError()
```

### 4.3 リソースレベルのアクセス制御

```
User A → API Key A (scope: chat.complete)
         └─ Can access Models: qwen-coder
         └ Can access Pools: * (但し owner=User A)

User B → API Key B (scope: admin)
         └─ Can access any Pool/Agent/Job
```

---

## 5. パスワード・シークレット管理

### 5.1 Database Credential

```python
# .env または環境変数
DATABASE_URL=postgresql://user:pass@localhost/ollama_cp
```

**保護方法**:
- .env は git に commit しない (.gitignore)
- CI/CDでは環境変数で注入
- Kubernetes Secret / Docker Secret を活用

### 5.2 JWT Secret

```python
# 環境変数
CONTROLLER_SECRET=<strong-random-256-bit-key>
```

**生成**:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 5.3 TLS秘密鍵

```bash
# Let's Encryptの場合
/etc/letsencrypt/live/control-plane.local/privkey.pem

# 手動の場合
/etc/control-plane/tls/server.key
chmod 600 /etc/control-plane/tls/server.key
```

---

## 6. レート制限と DoS対策

### 6.1 APIレート制限

```
By API Key:
- Default: 60 requests/minute
- Premium: 1000 requests/minute
- Admin: Unlimited (または 10000/min)

By Endpoint:
- /agents/register: 5 requests/hour
- /agents/poll: No limit (but within agent's registered rate)
- /v1/chat/completions: Per-user quota
```

**実装**:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/v1/chat/completions")
@limiter.limit("60/minute")
async def chat_completions(request):
    ...
```

### 6.2 コネクション数制限

```
Max connections per Agent Host: 10
Max concurrent polling: configured per agent (max_concurrency)
Max queue size: 10,000 jobs
```

---

## 7. 監査ログとコンプライアンス

### 7.1 記録すべきイベント

```json
{
  "timestamp": "2026-04-14T10:30:00Z",
  "event_type": "api_call",
  "actor": {
    "type": "user",
    "id": "user-xxx",
    "api_key_id": "key-yyy"
  },
  "resource": {
    "type": "job",
    "id": "job-zzz",
    "model": "qwen-coder"
  },
  "action": "job_submitted",
  "status": "success",
  "details": {
    "prompt_tokens": 50,
    "max_tokens": 2048,
    "temperature": 0.7
  },
  "ip_address": "192.168.1.100",
  "user_agent": "python/3.9 + openai/1.0"
}
```

### 7.2 ログ保持・削除ポリシー

```
- 最低90日間保持 (GDPR準拠)
- 監査ログは改ざん防止 (append-only, signing)
- 定期的なアーカイブ (S3等)
```

---

## 8. インシデント対応

### 8.1 トークン漏洩时

1. **Immediate**:
   - 当該トークンを無効化
   - token_reviled フラグをDBに記録
   - ユーザーに通知

2. **Post incident**:
   - 影響範囲を監査ログから特定
   - 不正アクセスの痕跡がないか確認
   - トークン更新を指示

### 8.2 キー漏洩時

1. **Immediate**:
   - APIキーを無効化 (revoke)
   - 新しいキーを再発行
   - 関連する全ジョブを監査

2. **Notification**:
   - ユーザーに緊急通知
   - 推奨アクション（キー更新）の提示

---

## 9. セキュリティチェックリスト

- [ ] TLS 1.2+ で全通信を暗号化
- [ ] mTLS for Agent ↔ Controller (推奨)
- [ ] APIキー・トークンを DB内でハッシュ化
- [ ] JWT の署名検証
- [ ] レート制限実装
- [ ] 秘密鍵を環境変数またはSecret Managerから読み込み
- [ ] 監査ログ記録（append-only）
- [ ] HSTS、CSP、X-Frame-Options ヘッダ設定
- [ ] SQL インジェクション対策（ORM使用、Prepared Statements）
- [ ] CSRF トークン（Web UI の場合）
- [ ] ログイン失敗時の遅延（ブルートフォース対策）
- [ ] 秘密鍵は git に commit しない
- [ ] 定期的なセキュリティ監査
- [ ] OpenAI SDK, Anthropic SDK の最新版使用

