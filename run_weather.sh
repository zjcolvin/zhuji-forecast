#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$(dirname "$0")" || exit 1
source weather.env
python3 zhuji_weather.py >> /tmp/weather_cron.log 2>&1
