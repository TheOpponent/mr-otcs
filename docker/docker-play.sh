#!/bin/bash

FFMPEG_IMAGE=ffmpeg
VIDEOPATH=$(realpath $1)
VIDEOFILE=$(basename $VIDEOPATH)
VIDEODIR=$(dirname $VIDEOPATH)
[ ! -z "$1" ] && VIDEOINPUT="-i /ffmpeg-media/$VIDEOFILE"
[ ! -z "$1" ] && VIDEOMOUNT="--volume $VIDEODIR:/ffmpeg-media:ro"

set -ex

docker run \
  --rm \
  --network host \
  --device '/dev/vchiq:/dev/vchiq' \
  $VIDEOMOUNT \
  $FFMPEG_IMAGE \
    -re \
    $VIDEOINPUT \
    -c:v h264_omx \
    -b:v 2500k \
    -acodec libfdk_aac \
    -b:a 160k \
    -vf "scale=w=1280:h=720:force_original_aspect_ratio=1,pad=1280:720:(ow-iw)/2:(oh-ih)/2" \
    -async 1 \
    -f flv \
    -g 60 \
    -r 60 \
    rtmp://127.0.0.1:1935/live/
