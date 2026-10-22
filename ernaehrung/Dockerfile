# Python 3.13 auf Alpine (Multi-Arch-Basis von Home Assistant, wie beim Fit Coach)
FROM ghcr.io/home-assistant/base-python:3.13-alpine3.24

RUN apk add --no-cache tzdata \
 && pip3 install --no-cache-dir --break-system-packages \
      "flask>=3,<4" "waitress>=3,<4" "requests>=2.32" "paho-mqtt>=2,<3" "openpyxl>=3.1,<4"

COPY app/ /app/
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
