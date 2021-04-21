#!/bin/bash

FFMPEG_OUTPUT=""
FFMPEG_PATH="/home/pi/ffmpeg-hls-pts-discontinuity-reclock/ffmpeg"
NGINX_PATH="/usr/local/nginx/sbin/nginx"

pgrep -x nginx >/dev/null

if [ $? -eq 1 ]
then
    sudo $NGINX_PATH
fi

while :
do
    $FFMPEG_PATH -i rtmp://localhost:1935/live -loglevel error -vcodec copy -acodec copy -f flv $FFMPEG_OUTPUT 2>&1 | tee -a >(ts "%b %d %Y %H:%M:%S" >> ffmpeg_error.log)

    echo -e "ffmpeg terminated. Restarting..." >&2
    sleep 1

done
