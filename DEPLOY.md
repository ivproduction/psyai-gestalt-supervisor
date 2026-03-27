# Деплой на Google Cloud — команды и настройки

## Google Cloud VM

### Создание VM (через gcloud CLI)

```bash
# Установить gcloud CLI (macOS)
brew install google-cloud-sdk

# Авторизация и выбор проекта
gcloud init

# Создать VM
gcloud compute instances create psyai-vm \
  --project=YOUR_PROJECT_ID \
  --zone=us-central1-f \
  --machine-type=e2-medium \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=20GB \
  --tags=http-server,https-server
```

**Параметры VM:**
- Machine type: `e2-medium` (2 vCPU, 4 GB RAM)
- Zone: `us-central1-f`
- OS: Debian 12
- Billing: Standard (не Spot)
- IP: `136.114.243.136`

---

## Firewall

```bash
# HTTP + HTTPS (для Caddy)
gcloud compute firewall-rules create allow-http-https \
  --allow tcp:80,tcp:443 \
  --source-ranges 0.0.0.0/0

# Portainer UI
gcloud compute firewall-rules create allow-9000 \
  --allow tcp:9000 \
  --source-ranges 0.0.0.0/0

gcloud compute firewall-rules create allow-9443 \
  --allow tcp:9443 \
  --source-ranges 0.0.0.0/0
```

> Порт 8000 наружу не открываем — трафик идёт через Caddy.

---

## Подключение к VM

```bash
# Через браузер Google Cloud Console → VM instances → SSH

# Или через gcloud
gcloud compute ssh psyai-vm --zone=us-central1-f
```

---

## Установка Docker на VM

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

---

## Установка Portainer

```bash
docker volume create portainer_data

docker run -d \
  -p 9443:9443 \
  -p 9000:9000 \
  --name portainer \
  --restart=always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data \
  portainer/portainer-ce:latest
```

**Portainer UI:** `http://136.114.243.136:9000`

---

## Caddy (reverse proxy + SSL)

Репо: `https://github.com/ivproduction/caddy-proxy`

```bash
# Создать общую сеть (один раз)
docker network create caddy-public
```

**Portainer → Stacks → Add stack → Repository:**

| Поле | Значение |
|---|---|
| Name | `caddy` |
| Repository URL | `https://github.com/ivproduction/caddy-proxy` |
| Branch | `refs/heads/master` |
| Compose path | `docker-compose.yml` |

Caddy автоматически получает SSL сертификат от Let's Encrypt.

**Добавить нового бота:**
1. DNS запись `bot-name.psycho-pocket.com → 136.114.243.136`
2. Строчка в `Caddyfile`: `bot-name.psycho-pocket.com { reverse_proxy bot-container:8000 }`
3. Пуш → Portainer redeploy caddy

---

## Деплой приложения

**Portainer → Stacks → Add stack → Repository:**

| Поле | Значение |
|---|---|
| Name | `gestalt-supervisor` |
| Repository URL | `https://github.com/ivproduction/psyai-gestalt-supervisor` |
| Branch | `refs/heads/master` |
| Compose path | `docker-compose.yml` |

**Environment variables:**
```
GEMINI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
ADMIN_API_KEY=...
WEBHOOK_SECRET=...
TELEGRAM_MODE=webhook
WEBHOOK_URL=https://gestalt-supervisor.psycho-pocket.com
```

---

## Безопасность

| Эндпоинт | Защита |
|---|---|
| `POST /webhook/gestalt-supervisor` | Открыт + проверка `X-Telegram-Bot-Api-Secret-Token` |
| `GET /swagger` | Открыт (требует API Key для действий) |
| `GET/POST /api/admin/*` | API Key (`X-API-Key` заголовок) |
| `POST /api/app/ask` | API Key (`X-API-Key` заголовок) |

**Использование Swagger:**
1. Открыть `https://gestalt-supervisor.psycho-pocket.com/swagger`
2. Нажать **Authorize** → вставить `ADMIN_API_KEY`

**Через curl:**
```bash
curl -H "X-API-Key: YOUR_ADMIN_API_KEY" \
  https://gestalt-supervisor.psycho-pocket.com/api/admin/collections
```

---

## Загрузка книг в Qdrant

### Вариант A — через API (конвертация на сервере)

```
1. POST /api/admin/files/upload       — загрузить PDF
2. POST /api/admin/files/convert      — PDF → Markdown (~2-3 мин)
   ?filename=book.pdf&mode=smart&source_type=session_guides
3. POST /api/admin/files/ingest       — Markdown → Qdrant
   ?filename=smart:book.txt&source_type=session_guides
4. GET  /api/admin/search             — проверить качество
   ?query=сопротивление&source_type=session_guides&mode=smart
```

### Вариант B — загрузить готовые .txt через SSH

```bash
# Закинуть файлы на VM
scp -i ~/.ssh/google_compute_engine \
  data/docs/smart/book.txt \
  data/docs/smart/book.meta.json \
  username@136.114.243.136:/tmp/

# Скопировать в контейнер
docker exec gestalt-supervisor-app-1 mkdir -p /app/data/docs/smart
docker cp /tmp/book.txt gestalt-supervisor-app-1:/app/data/docs/smart/
docker cp /tmp/book.meta.json gestalt-supervisor-app-1:/app/data/docs/smart/

# Ingest
curl -H "X-API-Key: YOUR_ADMIN_API_KEY" -X POST \
  'https://gestalt-supervisor.psycho-pocket.com/api/admin/files/ingest?filename=smart:book.txt&source_type=session_guides'
```

### Re-ingest

```bash
curl -H "X-API-Key: YOUR_ADMIN_API_KEY" -X POST \
  'https://gestalt-supervisor.psycho-pocket.com/api/admin/files/ingest?filename=smart:book.txt&source_type=session_guides'
```

---

## Полезные команды на VM

```bash
# Статус контейнеров
docker ps

# Логи приложения
docker logs gestalt-supervisor-app-1 -f

# Удалить все контейнеры (перед пересозданием стека)
docker rm -f $(docker ps -aq)
```

---

## Проблемы и решения

| Проблема | Причина | Решение |
|---|---|---|
| `service account not found` | Удалён дефолтный SA | Создать `compute-default` в IAM |
| `ZONE_RESOURCE_POOL_EXHAUSTED` | Нет ресурсов в зоне | Переключиться на другую зону |
| `port already allocated` | Порт занят другим контейнером | Найти и остановить контейнер |
| `reference not found` | Ветка `main` не существует | Использовать `refs/heads/master` |
| `network caddy-public not found` | Сеть не создана | `docker network create caddy-public` |
| Portainer: stack created outside | Контейнеры от старого запуска | `docker rm -f $(docker ps -aq)` |
| `telegram.error.Conflict` | Два бота работают одновременно | Остановить локальный: `docker compose down` |
| `embeddings: {}` в `/files/status` | Неверный `source_file` в Qdrant | Re-ingest всех файлов |
