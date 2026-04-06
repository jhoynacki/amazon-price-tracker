#!/usr/bin/env bash
# Amazon Price Tracker — First-time setup script
set -euo pipefail

echo "=== Amazon Price Tracker Setup ==="

# 1. Check dependencies
for cmd in docker docker-compose openssl python3; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: $cmd is required but not installed." >&2
    exit 1
  fi
done

# 2. Create .env from template if it doesn't exist
if [ ! -f .env ]; then
  cp .env.template .env
  echo "Created .env from template — fill in your secrets before continuing."
  # Generate random SECRET_KEY and TOKEN_ENCRYPTION_KEY
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  FERNET=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "INSTALL_CRYPTOGRAPHY_FIRST")
  PGPASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
  sed -i.bak "s|your-random-secret-key-at-least-32-chars.*|${SECRET}|" .env
  sed -i.bak "s|your-fernet-key-here=|${FERNET}|" .env
  sed -i.bak "s|strong-random-password|${PGPASS}|g" .env
  rm -f .env.bak
  echo "Generated random SECRET_KEY, TOKEN_ENCRYPTION_KEY, and POSTGRES_PASSWORD."
  echo "IMPORTANT: Edit .env and add your Amazon API credentials before proceeding."
  exit 0
fi

# 3. Build and start services
echo "Building Docker images..."
docker-compose build

echo "Starting database and Redis..."
docker-compose up -d db redis

echo "Waiting for database to be ready..."
sleep 5

echo "Running database migrations..."
docker-compose run --rm backend alembic upgrade head

echo "Starting all services..."
docker-compose up -d

echo ""
echo "=== Setup complete! ==="
echo "Dashboard: https://jack-hoy.com/amazon/"
echo "Flower:    http://localhost:5555/"
echo ""
echo "Next steps:"
echo "  1. Set up SSL: ./scripts/ssl.sh"
echo "  2. Configure Nginx to proxy jack-hoy.com/amazon → this server"
