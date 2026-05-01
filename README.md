# Ollama Control Plane

ローカルPCで動く Ollama モデルをエージェント化し、中央の Controller がジョブを配布するシステムです。  
OpenAI 互換 API (`/v1/chat/completions`) でアクセスできます。

```
クライアント (Python/curl 等)
    │  HTTPS  POST /v1/chat/completions
    ▼
Controller Server (Ubuntu + Docker + Nginx + Let's Encrypt)
    │  HTTPS  polling / job dispatch
    ▼
Agent Host (Windows WSL2 + Docker + Ollama)
    │  localhost
    ▼
Ollama (qwen2.5-coder:14b 等)
```

---

## 1. Controller サーバのセットアップ（Ubuntu Server）

### 前提

- Ubuntu Server 22.04 LTS
- Nginx インストール済み・起動中
- ドメインの A レコードをサーバ IP に向けている（例: `ocp.example.org`）
- `ubuntu` ユーザーで SSH ログイン可能

### 1-1. Docker CE インストール

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# シェルを再ログインするか以下を実行
newgrp docker
```

### 1-2. Let's Encrypt 証明書取得

certbot が未インストールの場合:

```bash
sudo apt-get install -y certbot
```

証明書取得（webroot 方式。既存サイトの `/var/www/html` を使用）:

```bash
sudo certbot certonly --webroot -w /var/www/html -d ocp.example.org
```

取得した証明書は `/etc/letsencrypt/live/ocp.example.org/` に保存されます。

自動更新の確認:

```bash
sudo systemctl status certbot.timer
```

### 1-3. Nginx バーチャルホスト追加

既存の Nginx 設定を壊さず、新しいファイルとして追加します。

```bash
sudo nano /etc/nginx/sites-available/ocp.example.org.conf
```

以下を貼り付け（`ocp.example.org` を自分のドメインに変更）:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name ocp.example.org;

    # Let's Encrypt 更新用（webroot 共有）
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ocp.example.org;

    ssl_certificate     /etc/letsencrypt/live/ocp.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ocp.example.org/privkey.pem;

    # ジョブ待機のロングポーリング（30秒）に対応
    proxy_read_timeout 60s;

    location / {
        proxy_pass         http://127.0.0.1:8200;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

有効化してリロード:

```bash
sudo ln -s /etc/nginx/sites-available/ocp.example.org.conf /etc/nginx/sites-enabled/
sudo nginx -t        # 設定テスト
sudo systemctl reload nginx
```

### 1-4. Controller デプロイ

```bash
# コードをサーバに配置
sudo mkdir -p /opt/ollama-control-plane
sudo chown $USER:$USER /opt/ollama-control-plane
cd /opt/ollama-control-plane
git clone <このリポジトリの URL> .
# または scp / rsync でコピー

cd controller
```

`.env` ファイルを作成（値は必ず自分で生成したランダム文字列に変える）:

```bash
cat > .env << 'EOF'
DATABASE_URL=sqlite+aiosqlite:///./data/controller.db
CONTROLLER_SECRET=<openssl rand -base64 32 で生成>
JWT_ALGORITHM=HS256
LISTENER_TOKEN_TTL_HOURS=2
POLL_TIMEOUT_SECONDS=30
JOB_TIMEOUT_SECONDS=300
ADMIN_API_KEY=<openssl rand -base64 32 で生成>
EOF
```

シークレットの生成方法:

```bash
openssl rand -base64 32
```

起動:

```bash
sudo docker compose up -d
```

ヘルスチェック:

```bash
curl -s https://ocp.example.org/health
# {"status":"ok"} が返れば OK
```

### 1-5. 招待トークンと API キーの発行

エージェントを登録するための招待トークン（1回限り）:

```bash
curl -s -X POST https://ocp.example.org/admin/tokens/invite \
  -H "Authorization: Bearer <ADMIN_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"pool_id": "default", "max_uses": 1}'
```

クライアントが `/v1/chat/completions` を呼ぶ API キー:

```bash
curl -s -X POST https://ocp.example.org/admin/api-keys \
  -H "Authorization: Bearer <ADMIN_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-key", "user_id": "user-1"}'
```

---

## 2. Agent Host のセットアップ（Windows WSL2）

### 前提

- WSL2 Ubuntu 22.04 が起動している
- Docker（`docker.io` または Docker CE）と `docker compose` が使える状態
- RTX GPU 搭載 PC 推奨（CPU でも動作可）

### 2-1. Ollama インストール

WSL2 ターミナルで実行:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

インストール後、サービスの起動確認:

```bash
systemctl is-active ollama   # "active" と表示されれば OK
```

サービスが起動していない場合:

```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

### 2-2. Ollama をコンテナからアクセスできるよう設定

デフォルトでは Ollama は `127.0.0.1:11434` にしかバインドされておらず、Docker コンテナから届きません。  
`/etc/systemd/system/ollama.service` を編集して全インターフェースにバインドします。

```bash
sudo nano /etc/systemd/system/ollama.service
```

`[Service]` セクションに以下の行を追加:

```ini
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

追加後の `[Service]` セクション例:

```ini
[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

設定を反映して再起動:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

確認（`*:11434` に変わっていれば OK）:

```bash
ss -tlnp | grep 11434
# LISTEN 0  4096  *:11434  *:*
```

### 2-3. モデルのダウンロード

使いたいモデルを `ollama pull` でダウンロードします。複数インストールしておけばクライアントから呼び分けられます。

```bash
ollama pull qwen2.5-coder:14b   # コーディング向け（約 9GB）
ollama pull gemma3:12b          # 汎用（約 8GB）
```

インストール済みモデルの確認:

```bash
ollama list
```

> **VRAM の目安（RTX 5060 Ti 16GB の場合）**  
> Ollama は一度に1モデルをロードします。16GB VRAM に収まるモデルであれば追加可能です。  
> - 7〜9B パラメータ (Q4): 約 4〜6GB  
> - 12〜14B パラメータ (Q4): 約 7〜9GB  
> - 27B パラメータ (Q4): 約 16GB 以上（収まらない場合あり）

### 2-4. Agent Host のデプロイ

コードを WSL2 内に配置:

```bash
sudo mkdir -p /opt/ollama-control-plane
sudo chown $USER:$USER /opt/ollama-control-plane
cd /opt/ollama-control-plane
git clone <このリポジトリの URL> .
# または Windows 側からコピー: cp /mnt/c/Develop/ollama-control-plane/agent-host . -r

cd agent-host
mkdir -p data
```

`.env` ファイルを作成（`INVITATION_TOKEN` は 1-5 で取得した値）:

```bash
cat > .env << 'EOF'
CONTROLLER_URL=https://ocp.example.org
INVITATION_TOKEN=inv_xxxxxxxxxx
OLLAMA_URL=http://host.docker.internal:11434
MAX_CONCURRENT_JOBS=2
CONFIG_DIR=/app/data
EOF
```

起動:

```bash
sudo docker compose up -d
```

ログでエージェント登録を確認:

```bash
sudo docker logs agent-host-agent-host-1 -f
```

以下のようなログが出れば成功:

```
INFO  core.agent: Discovered Ollama models: ['qwen2.5-coder:14b']
INFO  core.agent: Registering with Controller at https://ocp.example.org ...
INFO  core.agent: Registration successful. agent_id=ag-xxxxxxxx
INFO  core.agent: Agent ag-xxxxxxxx ready. Starting polling loop...
```

一度登録が完了すると、`data/agent.json` に設定が保存されます。  
次回起動時は `INVITATION_TOKEN` を使わず自動的にポーリングを再開します。

---

## 3. クライアントからの接続

### Python CLI（このリポジトリの `chat.py`）

```bash
pip install httpx
python chat.py --url https://ocp.example.org --key sk-proj-xxxxxxxx
```

オプション:

```
--url    Controller URL（デフォルト: https://ocp.pontium.org）
--key    API キー（環境変数 OCP_API_KEY でも指定可）
--model  モデル名（デフォルト: qwen2.5-coder:14b）
```

モデルを切り替える場合は `--model` で指定します:

```bash
python chat.py --key sk-proj-xxxxxxxx --model gemma3:12b
```

利用可能なモデルの一覧は `/v1/models` で確認できます:

```bash
curl -s https://ocp.example.org/v1/models \
  -H "Authorization: Bearer sk-proj-xxxxxxxx"
```

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://ocp.example.org/v1",
    api_key="sk-proj-xxxxxxxx",
)

response = client.chat.completions.create(
    model="qwen2.5-coder:14b",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

### curl

```bash
curl -s -X POST https://ocp.example.org/v1/chat/completions \
  -H "Authorization: Bearer sk-proj-xxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder:14b",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

---

## 4. 運用

### Controller の再起動・更新

```bash
# Ubuntu Server 上で
cd /opt/ollama-control-plane/controller
sudo docker compose down
sudo docker compose up -d --build
```

### Agent Host の再起動

```bash
# WSL2 上で
cd /opt/ollama-control-plane/agent-host
sudo docker compose restart
```

### モデルの追加

1. WSL2 で `ollama pull <モデル名>` を実行
2. Agent Host コンテナを再起動する

```bash
ollama pull gemma3:12b
sudo docker compose -f /opt/ollama-control-plane/agent-host/docker-compose.yml restart
```

Agent Host は起動時に Ollama からモデル一覧を取得し、最初のポーリング（最大30秒）で Controller に通知します。  
以降はクライアントから `model` フィールドで呼び分けられます。

> **注意**: `ollama pull` だけでは Controller に反映されません。コンテナの再起動が必要です。

### ログ確認

```bash
# Controller（Ubuntu Server）
ssh ubuntu@ocp.example.org
cd /opt/ollama-control-plane/controller
sudo docker compose logs -f

# Agent Host（WSL2）
sudo docker logs agent-host-agent-host-1 -f
```

### 登録済みエージェントの確認

```bash
curl -s https://ocp.example.org/admin/agents \
  -H "Authorization: Bearer <ADMIN_API_KEY>"
```

### 追加エージェントの登録

別の PC でも同じ 2. の手順を実行します。招待トークンは PC ごとに新しく発行してください（`max_uses: 1`）。

---

## 5. プロジェクト構成

```
ollama-control-plane/
├── controller/            # FastAPI + SQLite + Docker
│   ├── api/               # /agents, /jobs, /v1, /admin エンドポイント
│   ├── core/              # 認証, スケジューラ, 設定
│   ├── db/                # SQLAlchemy モデル, マイグレーション
│   ├── tests/
│   ├── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── docker-compose.yml
├── agent-host/            # Ollama ポーリングエージェント + Docker
│   ├── auth/              # JWT トークン管理
│   ├── config/            # 設定読み込み
│   ├── core/              # ポーリングループ, Ollama クライアント
│   ├── job/               # ジョブハンドラ
│   ├── tests/
│   ├── agent_host.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/                  # 設計ドキュメント
├── chat.py                # Python CLI クライアント
└── README.md
```

---

## 6. 認証フロー概要

```
[初回登録]
招待トークン(inv_xxx) → POST /agents/register
                      ← listener_token(JWT 2h) + refresh_token(30d)

[ポーリング中]
listener_token → POST /agents/poll → ジョブあり: 200 + job / なし: 204
               → 残り30分を切ったら POST /agents/token/refresh で自動更新

[クライアント]
API キー(sk-proj-xxx) → POST /v1/chat/completions → 結果を待機(最大300秒)
```

---

**Last Updated**: 2026-05-01  
**Status**: Phase 1 MVP 稼働中
