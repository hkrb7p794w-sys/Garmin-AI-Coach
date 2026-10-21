ARG BUILD_FROM
FROM $BUILD_FROM
RUN apk add --no-cache python3 py3-pip
RUN pip install --no-cache-dir --break-system-packages flask garminconnect paho-mqtt requests
COPY app.py /app.py
COPY ha_publish.py /ha_publish.py
COPY ai_coach.py /ai_coach.py
COPY fit_exercises.py /fit_exercises.py
COPY suggestions.py /suggestions.py
COPY chat.py /chat.py
COPY decoupling.py /decoupling.py
COPY plan.py /plan.py
COPY recommendation.py /recommendation.py
COPY progress.py /progress.py
COPY exercise_names.py /exercise_names.py
COPY gym_progress.py /gym_progress.py
COPY hr_zones.py /hr_zones.py
COPY garmin_swim.py /garmin_swim.py
COPY ha_settings.py /ha_settings.py
COPY tagesform.py /tagesform.py
COPY garmin_gym.py /garmin_gym.py
COPY gym_prefill.py /gym_prefill.py
COPY sleep.py /sleep.py
COPY competition.py /competition.py
COPY pace_check.py /pace_check.py
COPY run_plan.json /run_plan.json
COPY gym_plan.json /gym_plan.json
COPY gym_exercises.json /gym_exercises.json
COPY swim_plan.json /swim_plan.json
COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
