#!/usr/bin/env bash
# Run on the "portfolio" host by the deploy job of release.yml: `ssh ... 'bash -s' < deploy.sh`.
#
# One-time prerequisites on the host, for the SSH user of the SERVER_USERNAME secret:
#   - member of the `docker` group (`sudo usermod -aG docker <user>`, then log in again)
#   - the GHCR package is public (the repository is), so no `docker login` is needed. After
#     the first release, check Packages > api-jouskaio.me > Package settings > Visibility.
#   - APP_DIR below holds a `.env` made from .env.example, and a writable `data/` folder
set -euo pipefail

APP_DIR="/home/user/Documents/api.jouskaio.me"

cd "${APP_DIR}"

echo "Pulling the latest image..."
docker compose pull

echo "Restarting the API..."
docker compose up -d --remove-orphans

echo "Waiting for the API to answer..."
for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS http://127.0.0.1:2000/api/v1/health > /dev/null; then
        echo "API is up."
        exit 0
    fi
    sleep 3
done

echo "API did not answer in time:" >&2
docker compose logs --tail 40 api >&2
exit 1
