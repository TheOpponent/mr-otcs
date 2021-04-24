#!/bin/bash

./docker-build.sh

FFMPEG_OUTPUT="$1"
FFMPEG_IMAGE=ffmpeg
FFMPEG_CONTAINER=ffmpeg-hls
NGINX_IMAGE=nginx-rtmp
NGINX_CONTAINER=nginx-rtmp

docker stop $FFMPEG_CONTAINER $NGINX_CONTAINER
docker rm $FFMPEG_CONTAINER $NGINX_CONTAINER

docker run \
  --name $NGINX_CONTAINER \
  -p 1935:1935/tcp \
  --restart unless-stopped \
  --detach \
  $NGINX_IMAGE

docker run \
  --name $FFMPEG_CONTAINER \
  --network host \
  --restart unless-stopped \
  --detach \
  $FFMPEG_IMAGE \
    -i rtmp://127.0.0.1:1935/live \
    -loglevel error \
    -vcodec copy \
    -acodec copy \
    -f flv \
    $FFMPEG_OUTPUT

