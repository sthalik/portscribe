FROM alpine:latest
LABEL org.opencontainers.image.title="portscribe"
WORKDIR /app

COPY requirements.txt portscribe.py .

RUN \
set -euo pipefail; \
apk add --no-cache chromium chromium-chromedriver python3 py3-pip curl; \
pip install -U -r requirements.txt \
  --root-user-action=ignore --no-cache-dir --break-system-packages; \
rm requirements.txt; \
addgroup -g 6002 -S appgroup && adduser -u 6002 -H -h /tmp -S -G appgroup appuser; \
chmod 750 /app; \
chgrp appgroup /app;

VOLUME ["/app/state"]

CMD ["/bin/sh", "-c", "cd /app/state && python /app/portscribe.py"]
