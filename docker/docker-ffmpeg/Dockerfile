# --- build
FROM balenalib/rpi-raspbian:buster AS builder

ENV INITSYSTEM on
ENV BINDIR="/usr/local/bin"
ENV FFMPEG_SRC_URL="https://github.com/jjustman/ffmpeg-hls-pts-discontinuity-reclock/archive/f46551d510573b3a132dba0c52adf19101e2223a.tar.gz"
ENV FFMPEG_SRC_DIR="/usr/local/src/ffmpeg"

ENV DEBIAN_FRONTEND=noninteractive

# For whatever reason, if ca-certificates isn't removed first then
# the current certs don't get installed (and curl doesn't like that)
RUN \
  apt-get -q update &&\
  apt-get purge ca-certificates &&\
  apt-get install --no-install-recommends -qy apt-utils ca-certificates curl build-essential pkg-config git cmake

# build rpi userspace libs
WORKDIR "/usr/local"
RUN git clone --depth 1 https://github.com/raspberrypi/userland.git
WORKDIR "/usr/local/userland"
RUN ./buildme && echo "/opt/vc/lib" > /etc/ld.so.conf.d/00-vmcs.conf && ldconfig

# add deb-multimedia repo
RUN \
  echo "deb     http://www.deb-multimedia.org buster main non-free" >> /etc/apt/sources.list.d/zz-deb-multimedia.list &&\
  echo "deb-src http://www.deb-multimedia.org buster main non-free" >> /etc/apt/sources.list.d/zz-deb-multimedia.list

# keep deb-multimedia's unsigned packages from taking priority over debian ones
RUN \
  echo "Package: *"                         >> /etc/apt/preferences.d/zz-deb-multimedia &&\
  echo "Pin: origin www.deb-multimedia.org" >> /etc/apt/preferences.d/zz-deb-multimedia &&\
  echo "Pin-Priority: 100"                  >> /etc/apt/preferences.d/zz-deb-multimedia

RUN \
  apt-get update -oAcquire::AllowInsecureRepositories=true &&\
  apt-get -qy install --no-install-recommends --allow-unauthenticated deb-multimedia-keyring

# ffmpeg dependencies available through Debian
RUN apt-get install --no-install-recommends -qy \
  libaom-dev \
  libass-dev \
  libdav1d-dev \
  libdrm-dev \
  libfontconfig1-dev \
  libfreetype6-dev \
  libgmp-dev \
  libmp3lame-dev \
  libopencore-amrnb-dev \
  libopencore-amrwb-dev \
  libopenjp2-7-dev \
  libopus-dev \
  libomxil-bellagio-dev \
  librtmp-dev \
  libsnappy-dev \
  libsoxr-dev \
  libssh-dev \
  libssl-dev \
  libwebp-dev \
  libxml2-dev \
  libtheora-dev \
  libvorbis-dev \
  libvpx-dev \
  libwavpack-dev \
  libx264-dev \
  libx265-dev \
  libxvidcore-dev

# ffmpeg dependencies available through deb-multimedia (unauthenticated)
RUN apt-get -qy install --allow-unauthenticated \
  libfdk-aac-dev \
  libkvazaar-dev \
  libzimg-dev

# prepare to build
ENV CPUCOUNT=4
WORKDIR ${FFMPEG_SRC_DIR}

RUN curl -sD /dev/stderr -L ${FFMPEG_SRC_URL} | tar zx --strip-components=1

COPY config.sh .

RUN ./config.sh
RUN make -j${CPUCOUNT}
RUN make install

# --- install

FROM balenalib/rpi-raspbian:buster

RUN \
  apt-get -qq update &&\
  apt-get purge ca-certificates &&\
  apt-get install --no-install-recommends -qy apt-utils ca-certificates curl

COPY --from=builder /etc/apt /etc/apt
COPY --from=builder /var/lib/apt /var/lib/apt

# binary libs
RUN DEBIAN_FRONTEND=noninteractive \
apt-get install --no-install-recommends -qy \
  libaom0 \
  libass9 \
  libdav1d3 \
  libdrm2 \
  libfontconfig \
  libmp3lame0 \
  libopencore-amrwb0 \
  libopencore-amrnb0 \
  libopenjp2-7 \
  libopus0 \
  libsnappy1v5 \
  libssh-4 \
  libsoxr0 \
  libtheora0 \
  libx264-155 \
  libx265-165 \
  libvorbis0a \
  libvorbisenc2 \
  libvpx5 \
  libwavpack1 \
  libwebpmux3 \
  libxml2 \
  libxvidcore4

# binary libs (from deb-multimedia)
RUN DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends --allow-unauthenticated -qy \
  libfdk-aac2 \
  libkvazaar4 \
  libzimg2

COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /usr/local/lib /usr/local/lib
COPY --from=builder /usr/local/share /usr/local/share

ENTRYPOINT ["/usr/local/bin/ffmpeg"]
CMD ["--help"]
