#!/bin/bash

FFMPEG_IMAGE=ffmpeg
NGINX_IMAGE=nginx-rtmp

set -ex

time docker build -t $FFMPEG_IMAGE ./docker-ffmpeg
time docker build -t $NGINX_IMAGE ./docker-nginx

