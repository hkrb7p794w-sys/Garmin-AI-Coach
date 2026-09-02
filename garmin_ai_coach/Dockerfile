ARG BUILD_FROM
FROM $BUILD_FROM
RUN apk add --no-cache python3 py3-pip
RUN pip install --no-cache-dir --break-system-packages flask garminconnect
COPY app.py /app.py
COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]