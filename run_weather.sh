#!/bin/bash
cd "$(dirname "$0")" || exit 1
source weather.env
python3 zhuji_weather.py >> /tmp/weather_cron.log 2>&1
