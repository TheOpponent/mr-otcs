FROM balenalib/rpi-raspbian:buster

ENV NGINX_SRC_URL="http://nginx.org/download/nginx-1.19.10.tar.gz"
ENV NGINX_SRC_DIR="/usr/local/src/nginx"
ENV RTMP_SRC_DIR="/usr/local/src/rtmp"

RUN DEBIAN_FRONTEND=noninteractive \
  apt-get update && \
  apt-get purge ca-certificates && \
  apt-get install --no-install-recommends -qy apt-utils ca-certificates build-essential pkg-config curl git

WORKDIR ${NGINX_SRC_DIR}
RUN curl -sD /dev/stderr -L ${NGINX_SRC_URL} | tar zx --strip-components=1
RUN git clone --depth 1 https://github.com/arut/nginx-rtmp-module.git ${RTMP_SRC_DIR}

RUN DEBIAN_FRONTEND=noninteractive \
  apt-get install --no-install-recommends -qy libpcre3-dev libssl-dev zlib1g-dev

RUN ./configure \
  --sbin-path=/usr/local/sbin/nginx \
  --conf-path=/etc/nginx/nginx.conf \
  --error-log-path=/var/log/nginx/error.log \
  --pid-path=/var/run/nginx/nginx.pid \
  --lock-path=/var/lock/nginx/nginx.lock \
  --http-log-path=/var/log/nginx/access.log \
  --http-client-body-temp-path=/tmp/nginx-client-body \
  --with-threads \
  --with-ipv6 \
  --with-http_ssl_module \
  --add-module=${RTMP_SRC_DIR} \
&& make -j4 && make install

RUN \
  mkdir /var/lock/nginx &&\
  rm -rf /tmp/build && \
  ln -svf /dev/stdout /var/log/nginx/access.log && \
  ln -svf /dev/stderr /var/log/nginx/error.log

COPY nginx.conf /etc/nginx/nginx.conf

RUN nginx -t

EXPOSE 1935
CMD ["nginx", "-g", "daemon off;"]
