# Amazon Price Tracker

A production-ready web application deployed at `jack-hoy.com/amazon` that tracks prices for Amazon items you buy frequently and alerts you when they drop.

## Architecture

```
nginx (443/SSL) ──► /amazon  ──► FastAPI (uvicorn)
                              ──► PostgreSQL (price history, users, products)
                              ──► Redis + Celery (background price checks every 6h)
                              ──► Playwright scraper (PA-API fallback)
```

## Quick Start

```bash
# 1. Clone and set up environment
git clone <repo> && cd amazon-tracker
./scripts/setup.sh          # creates .env with random secrets

# 2. Edit .env — add your API keys (see sections below)
nano .env

# 3. Start everything
docker-compose up -d

# 4. Get SSL certificate (production only)
CERTBOT_EMAIL=you@example.com ./scripts/ssl.sh

# 5. Open https://jack-hoy.com/amazon
```

---

## Registering Amazon OAuth (Login with Amazon)

1. Go to: https://developer.amazon.com/loginwithamazon/console/site/lwa/overview.html
2. Click **Create a New Security Profile**
3. Fill in:
   - **Name**: Amazon Price Tracker
   - **Description**: Personal price tracking app
   - **Privacy URL**: `https://jack-hoy.com`
4. After creation, click **Web Settings** tab
5. Add **Allowed Return URL**: `https://jack-hoy.com/amazon/auth/callback`
6. Copy **Client ID** → `AMAZON_CLIENT_ID` in `.env`
7. Copy **Client Secret** → `AMAZON_CLIENT_SECRET` in `.env`

---

## Getting PA-API Keys (Product Advertising API v5)

> Requires an active Amazon Associates account with at least 3 qualifying sales.

1. Sign up at: https://affiliate-program.amazon.com/
2. Once approved, go to: https://affiliate-program.amazon.com/assoc_credentials/home
3. Click **Add credentials**
4. Copy:
   - **Access Key** → `PAAPI_ACCESS_KEY`
   - **Secret Key** → `PAAPI_SECRET_KEY`
   - **Tracking ID** (your associate tag) → `PAAPI_PARTNER_TAG`

If PA-API is unavailable, the app automatically falls back to a Playwright-based scraper.

---

## Pointing Nginx to jack-hoy.com/amazon

The included `nginx/nginx.conf` handles this. Key block:

```nginx
location /amazon {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

If you have an existing Nginx on your server (outside Docker), add:

```nginx
location /amazon {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## Deployment on DigitalOcean

```bash
# 1. Create a Droplet (Ubuntu 22.04, 2GB RAM minimum)
# 2. Point jack-hoy.com A record to droplet IP
# 3. SSH into droplet
ssh root@YOUR_DROPLET_IP

# 4. Install Docker
curl -fsSL https://get.docker.com | sh
apt-get install -y docker-compose-plugin

# 5. Clone repo
git clone <repo> /opt/amazon-tracker
cd /opt/amazon-tracker

# 6. Run setup
./scripts/setup.sh
nano .env   # add API keys
./scripts/setup.sh   # run again to start services

# 7. Get SSL
CERTBOT_EMAIL=you@example.com ./scripts/ssl.sh
```

## Deployment on Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Launch (creates fly.toml)
fly launch --name amazon-price-tracker

# Set secrets
fly secrets set SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
fly secrets set DATABASE_URL=postgresql://...
fly secrets set AMAZON_CLIENT_ID=...
fly secrets set AMAZON_CLIENT_SECRET=...
fly secrets set PAAPI_ACCESS_KEY=...
fly secrets set PAAPI_SECRET_KEY=...
fly secrets set PAAPI_PARTNER_TAG=...
fly secrets set TOKEN_ENCRYPTION_KEY=...

# Deploy
fly deploy
```

---

## Features

| Feature | Implementation |
|---------|---------------|
| Amazon OAuth login | Login with Amazon (LWA OAuth 2.0) |
| Order history import | CSV/ZIP upload + parser |
| Price data | PA-API v5 with key rotation |
| Scraper fallback | Playwright + rotating user agents + proxy support |
| Background checks | Celery + Redis beat (every 6h) |
| Alerts | Email (SMTP/SendGrid), SMS (Twilio), Telegram, Pushover |
| Price charts | ApexCharts (30-day history) |
| Security | Fernet-encrypted tokens, HTTPS, CSRF protection, rate limiting |

---

## Database Schema

```
users           — Amazon user ID, encrypted tokens/email, alert settings
products        — ASIN, title, image, current/list price, stock status
user_products   — Per-user tracking rules (target price, discount %, alert channels)
price_history   — Time-series price records (source: paapi | scraper)
```

### Run migrations manually

```bash
./scripts/migrate.sh upgrade head
./scripts/migrate.sh "downgrade -1"
```

---

## Security Notes

- Amazon OAuth tokens stored AES-256 encrypted (Fernet) in PostgreSQL
- No Amazon order content stored beyond ASINs and prices
- HTTPS enforced via Let's Encrypt (auto-renewal every 12h)
- Session cookies: `httponly`, `samesite=lax`, `secure` in production
- Auth endpoints rate-limited: 10 req/min per IP
- `client_max_body_size 60M` for order history uploads

---

## Monitoring

- **Flower** (Celery task monitor): `http://localhost:5555/`
- **FastAPI docs**: `https://jack-hoy.com/amazon/docs`
- **Logs**: `docker-compose logs -f backend celery_worker`
