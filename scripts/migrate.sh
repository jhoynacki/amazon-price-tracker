#!/usr/bin/env bash
# Run Alembic migrations inside the running backend container
set -euo pipefail

CMD="${1:-upgrade head}"
echo "Running: alembic $CMD"
docker-compose exec backend alembic $CMD
