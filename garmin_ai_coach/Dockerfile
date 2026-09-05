ARG BUILD_FROM
FROM $BUILD_FROM
RUN apk add --no-cache python3 py3-pip
RUN pip install --no-cache-dir --break-system-packages flask garminconnect paho-mqtt requests
COPY app.py /app.py
COPY ha_publish.py /ha_publish.py
COPY ai_coach.py /ai_coach.py
COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]