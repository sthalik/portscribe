FROM alpine:latest
LABEL org.opencontainers.image.title="portscribe"
WORKDIR /app

COPY requirements.txt .env.sample portscribe.py .

RUN \
apk add --no-cache chromium chromium-chromedriver; \
apk add --no-cache python3 py3-pip; \
apk add --no-cache curl; \
addgroup -g 6002 -S appgroup && adduser -u 6002 -H -h /tmp -S -G appgroup appuser; \
pip install -U -r requirements.txt \
  --root-user-action=ignore --no-cache-dir --break-system-packages; \
chmod 1770 /app; \
chgrp appgroup /app;

VOLUME ["/app/state"]

CMD ["/bin/sh", "-c", "cd /app/state && python /app/portscribe.py"]
