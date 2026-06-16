# Deploying the backend with Docker

The backend is packaged as a single image that bundles the website, the trained
model artifacts, and the `server` package it depends on.

## Prerequisites

- A `.env` file at the **repository root** with the device credentials
  (`EMAIL`, `PASSWORD`, `IP_LIGHT`, `TUYA_CLIENT_ID`, `TUYA_SECRET`,
  `TUYA_DEVICE_ID`). It is **not** baked into the image — it is read at runtime.
- The server must be on the **same LAN as the Arduino**, because the live
  collector receives the Arduino's TCP/UDP connection (ports 20000 / 12345).

## Option A — build and run on the server (docker compose)

```bash
docker compose -f website/docker-compose.yml up -d --build
# web UI: http://<server>:5000
```

## Option B — build once, export the image, load on the server

Build (from the repo root) and save the image to a file:

```bash
docker build -f website/Dockerfile -t iop-backend:latest .
docker save iop-backend:latest | gzip > iop-backend.tar.gz
```

Copy `iop-backend.tar.gz` and the root `.env` to the server, then:

```bash
docker load < iop-backend.tar.gz
docker run -d --name iop-backend \
  --network host \
  --env-file .env \
  --restart unless-stopped \
  iop-backend:latest
```

`--network host` is required so the container can bind the host's LAN IP and
receive the Arduino connection; the web UI is served on `host:5000`.

## Logs / stop

```bash
docker logs -f iop-backend
docker rm -f iop-backend           # plain docker run
docker compose -f website/docker-compose.yml down   # compose
```

## Notes

- The model artifacts (`ipc_model.pth`, `ipc_scaler.gz`, `ipc_meta.json`) are
  copied into the image at build time. Rebuild the image after retraining.
- `POST /api/estimate` collects live sweeps from the Arduino by default. For an
  offline smoke test without hardware, post `{"sample": true}` to predict on the
  bundled `input.csv`.
