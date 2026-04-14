# Ollama Control Plane

ローカルPC上の Ollama/Qwen Coder をエージェント化し、中央コントローラがジョブを配布するシステムです。
OpenAI互換API と Claude Code 接続の両方をサポートします。

## 🎯 目的

- **分散推論**: 複数PCのローカルLLM（Qwen Coder等）を一元管理
- **中央ジョブ配分**: Controller がエージェントプールへジョブを配布
- **複数インターフェース**: OpenAI SDK、Anthropic SDK、独自CLIから接続可能
- **セキュリティ**: TLS、短命トークン、API key認証により安全に運用

## 📚 ドキュメント

実装に先立ち、以下のドキュメントを参照してください（優先順）:

| ドキュメント | 目的 |
|-----------|------|
| [product-requirements.md](./docs/product-requirements.md) | 要件定義、システム全体像、ユースケース |
| [mvp-scope.md](./docs/mvp-scope.md) | MVP範囲、Phase 1-4の実装計画、タイムライン |
| [architecture.md](./docs/architecture.md) | システムアーキテクチャ、コンポーネント設計、データフロー |
| [api-spec.md](./docs/api-spec.md) | Agent API、User API、Admin API の仕様 |
| [security.md](./docs/security.md) | 認証設計、暗号化、認可、レート制限 |
| [agent-lifecycle.md](./docs/agent-lifecycle.md) | Agent Host のステートマシン、ポーリングフロー、トークン更新 |

## 🏗️ システム構成

```
┌─────────────────────────────────────────────────────┐
│           Client Applications                        │
│  (Python SDK, Claude Code, Node.js, Custom CLI)     │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  API Gateway/Proxy   │
        │ - /v1/chat/... (OpenAI)
        │ - /v1/messages (Anthropic)
        │ - API Key Auth
        └──────────────┬───────┘
                       │
                       ▼
        ┌──────────────────────┐
        │ Controller Server    │
        │ - Agent Registry     │
        │ - Job Queue          │
        │ - State Management   │
        │ - /agents/register   │
        │ - /agents/poll       │
        └──────────────┬───────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    ┌─────────┐  ┌─────────┐  ┌─────────┐
    │ Agent 1 │  │ Agent 2 │  │ Agent N │
    │ (PC-A)  │  │ (PC-B)  │  │ (PC-N)  │
    │         │  │         │  │         │
    │ Ollama  │  │ Ollama  │  │ Ollama  │
    │ qwen-   │  │ qwen-   │  │ gemma   │
    │ coder   │  │ coder   │  │         │
    └─────────┘  └─────────┘  └─────────┘
```

## 🚀 クイックスタート（MVP Phase）

### 前提条件

- **Agent Host**: Python 3.10+、Ollama 稼働中 (port 11434)
- **Controller**: Python 3.10+、PostgreSQL or SQLite
- **Client**: OpenAI SDK 1.0+、またはAnthropic SDK

### インストール & 実行

```bash
# 1. リポジトリクローン
git clone https://github.com/your-org/ollama-control-plane
cd ollama-control-plane

# 2. Controller サーバ起動
cd controller
pip install -r requirements.txt
export DATABASE_URL="sqlite:///./ollama_cp.db"
uvicorn main:app --host 0.0.0.0 --port 8000

# 3. 別ターミナル: Agent Host トークン生成
curl -X POST http://localhost:8000/admin/tokens/invite \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-key>" \
  -d '{"pool_id": "default", "expires_in_days": 7}'

# 4. Agent Host セットアップ・実行
cd ../agent-host
pip install -r requirements.txt
export INVITATION_TOKEN="inv_xxxxxx"
export CONTROLLER_URL="http://localhost:8000"
python agent_host.py

# 5. クライアント側でテスト
import openai
openai.api_key = "sk-test-key"
openai.base_url = "http://localhost:8000/"

response = openai.chat.completions.create(
    model="qwen-coder",
    messages=[{"role": "user", "content": "Write a hello world function"}]
)

print(response.choices[0].message.content)
```

## 🔐 セキュリティ

- **通信**: TLS 1.2 以上（mTLS 対応予定）
- **認証**: 招待トークン（初回登録）→ 短命 JWT（待受）
- **APIキー**: OpenAI互換、per-user quota、レート制限

詳細は [security.md](./docs/security.md) を参照。

## 📊 実装計画

### Phase 1 (MVP) - 4-6週間
- [x] ドキュメント作成
- [ ] Agent Host 基本実装
- [ ] Controller フレームワーク
- [ ] OpenAI /v1/chat/completions 対応

### Phase 2 - 3-4週間
- [ ] 複数Agent対応
- [ ] Agent Pool & スケジューリング
- [ ] ストリーミング対応

### Phase 3 - 3-4週間
- [ ] Claude Code 統合
- [ ] Anthropic互換エンドポイント
- [ ] Web管理UI

### Phase 4 - 2-3週間
- [ ] mTLS
- [ ] 詳細監査ログ
- [ ] 本番運用機能

詳細は [mvp-scope.md](./docs/mvp-scope.md) を参照。

## 🛠️ プロジェクト構成（予定）

```
ollama-control-plane/
├── docs/
│   ├── product-requirements.md
│   ├── architecture.md
│   ├── api-spec.md
│   ├── security.md
│   ├── agent-lifecycle.md
│   └── mvp-scope.md
├── controller/
│   ├── main.py
│   ├── requirements.txt
│   ├── database/
│   ├── api/
│   ├── core/
│   └── tests/
├── agent-host/
│   ├── agent_host.py
│   ├── requirements.txt
│   ├── config/
│   ├── core/
│   └── tests/
├── client-examples/
│   ├── python_sdk_example.py
│   ├── nodejs_sdk_example.js
│   └── custom_cli.py
├── docker-compose.yml
├── Dockerfile.controller
├── Dockerfile.agent-host
└── README.md
```

## 📖 用語集

| 用語 | 説明 |
|-----|------|
| **Agent Host** | 各PC上で動く常駐プロセス、Ollama/Qwen Coder を実行ノード |
| **Controller** | エージェント登録・認証・ジョブ配布・状態管理の中央サーバ |
| **Listener Token** | Agent Host がポーリング・待受に使う短命JWT |
| **Invitation Token** | Agent初回登録のみに使う一回限りトークン |
| **API Key** | ユーザーが OpenAI/Anthropic 互換API を呼び出す際の認証 |
| **Agent Pool** | エージェントの論理グループ（例: desktop-gpu, laptop-cpu） |
| **Job** | ユーザーから投入された推論リクエスト |

## 🤝 貢献

このプロジェクトは段階的に Claude Code を活用しながら実装を進めます。
各Phaseで基本設計と実装手順が明確なため、拡張・改善も容易です。

## 📝 ライセンス

（TBD）

## 📧 連絡先

質問・提案は Issue を通じてお願いします。

---

**Last Updated**: 2026-04-14  
**Phase**: Design & Documentation (Phase 0)
