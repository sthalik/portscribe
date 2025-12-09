FROM alpine:latest
LABEL org.opencontainers.image.title="portscribe"
WORKDIR /app

RUN apk add --no-cache chromium chromium-chromedriver
RUN apk add --no-cache python3 py3-pip
RUN apk add --no-cache curl

RUN addgroup -g 6002 -S appgroup && adduser -u 6002 -H -h /tmp -S -G appgroup appuser

COPY requirements.txt .env.sample portscribe.py .

RUN pip install -U -r requirements.txt \
    --root-user-action=ignore --no-cache-dir --break-system-packages

RUN chmod 1770 /app
RUN chgrp appgroup /app
VOLUME ["/app/state"]

CMD ["/bin/sh", "-c", "cd /app/state && python /app/portscribe.py"]
