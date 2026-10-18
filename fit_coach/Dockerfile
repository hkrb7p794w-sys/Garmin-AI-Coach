# Python 3.13 auf Alpine 3.24 (Multi-Arch-Basis von Home Assistant). garminconnect
# >= 0.3.19 braucht Python >= 3.12 und curl_cffi (Login über Garmins neues SSO);
# beides gibt es als fertige musl-Wheels für aarch64 (Raspberry Pi) und amd64.
FROM ghcr.io/home-assistant/base-python:3.13-alpine3.24

RUN apk add --no-cache tzdata \
 && pip3 install --no-cache-dir --break-system-packages \
      "garminconnect>=0.3.19,<0.4" "curl_cffi>=0.15" "paho-mqtt>=2,<3" "flask>=3,<4" "requests>=2.33"

COPY app/ /app/
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
