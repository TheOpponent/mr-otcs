#!/bin/bash

FFMPEG_OUTPUT=""

while :
do
     ./ffmpeg-hls-pts-discontinuity-reclock/ffmpeg -i rtmp://localhost:1935/source -loglevel error -vcodec copy -acodec copy -f flv $FFMPEG_OUTPUT 2>&1 | tee -a >(ts "%b %d %Y %H:%M:%S" >> ffmpeg_error.log)
    
    echo -e "ffmpeg terminated. Restarting..." >&2
    sleep 1

done
    
