#!/usr/bin/env bash
# Obtain Let's Encrypt certificate for jack-hoy.com
# Run AFTER Nginx is serving port 80 (HTTP)
set -euo pipefail

DOMAIN="jack-hoy.com"
EMAIL="${CERTBOT_EMAIL:-admin@jack-hoy.com}"

echo "=== Obtaining SSL certificate for $DOMAIN ==="

# Start Nginx on port 80 first (for ACME challenge)
docker-compose up -d nginx

echo "Running certbot..."
docker-compose run --rm certbot certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  -d "$DOMAIN" \
  -d "www.$DOMAIN"

echo "Reloading Nginx with SSL..."
docker-compose exec nginx nginx -s reload

echo "Certificate obtained! Nginx is now serving HTTPS."
echo "Auto-renewal is handled by the certbot container (checks every 12h)."
