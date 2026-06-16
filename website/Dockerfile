# Backend image for the Internet of Plants website.
#
# IMPORTANT: build from the repository ROOT, not from website/, because the
# backend imports the project's `server` package:
#
#   docker build -f website/Dockerfile -t iop-backend:latest .
#
FROM python:3.12-slim

WORKDIR /app

# install python deps first so this layer is cached across code changes.
# torch is pulled from the CPU index to avoid the huge CUDA wheels.
COPY website/requirements.txt website/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r website/requirements.txt gunicorn

# the backend needs BOTH the website code/artifacts and the server package
COPY server/ server/
COPY website/ website/

WORKDIR /app/website
EXPOSE 5000

# 1 worker (the live collector binds a fixed port, so concurrent collections
# would clash), a few threads so /api/health stays responsive while a sweep is
# being collected, and a long timeout because live collection can block ~30s.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", \
     "--timeout", "120", "backend:app"]
