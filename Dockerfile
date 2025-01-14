FROM alpine:3.16
MAINTAINER Lafeng<Lafeng@gmail.com>

ENV NODE_ID=0                     \
    DNS_1=1.0.0.1                 \
    DNS_2=8.8.8.8                 \
    SPEEDTEST=0                   \
    CLOUDSAFE=0                   \
    AUTOEXEC=0                    \
    ANTISSATTACK=0                \
    MU_SUFFIX=download.windowsupdate.com            \
    MU_REGEX=%suffix       \
    API_INTERFACE=webapi       \
    WEBAPI_URL=https://zhaoj.in   \
    WEBAPI_TOKEN=glzjin           \
    MYSQL_HOST=127.0.0.1          \
    MYSQL_PORT=3306               \
    MYSQL_USER=sspanel                 \
    MYSQL_PASS=ss                 \
    MYSQL_DB=sspanel          \
    REDIRECT=github.com           \
    DeviceOnlineMinTraffic=10       \
    FAST_OPEN=false

RUN  apk --no-cache add \
                        curl \
                       python3-dev \
                        libsodium-dev \
                        openssl-dev \
                        udns-dev \
                        mbedtls-dev \
                        pcre-dev \
                        libev-dev \
                        libtool \
                        libffi-dev            && \
     apk --no-cache add --virtual .build-deps \
                        git \
                        tar \
                        make \
                        py3-pip \
                        autoconf \
                        automake \
                        build-base \
                        linux-headers         && \
     ln -sf /usr/bin/python3 /usr/bin/python   && \
     ln -sf /usr/bin/pip3    /usr/bin/pip      && \
     git clone -b manyuser https://github.com/ShenKeeeew/smod.git "/root/shadowsocks" --depth 1 && \
     cd  /root/shadowsocks                    && \
     pip install --upgrade pip                && \
     pip install -r requirements.txt          && \
     rm -rf ~/.cache && touch /etc/hosts.deny && \
     apk del --purge .build-deps

WORKDIR /root/shadowsocks

CMD cp apiconfig.py userapiconfig.py &&                                        cp   config.json  user-config.json && \
    sed -i "s|NODE_ID = 0|NODE_ID = ${NODE_ID}|"                               /root/shadowsocks/userapiconfig.py && \
    sed -i "s|SPEEDTEST = 6|SPEEDTEST = ${SPEEDTEST}|"                         /root/shadowsocks/userapiconfig.py && \
    sed -i "s|CLOUDSAFE = 1|CLOUDSAFE = ${CLOUDSAFE}|"                         /root/shadowsocks/userapiconfig.py && \
    sed -i "s|AUTOEXEC = 0|AUTOEXEC = ${AUTOEXEC}|"                            /root/shadowsocks/userapiconfig.py && \
    sed -i "s|ANTISSATTACK = 0|ANTISSATTACK = ${ANTISSATTACK}|"                /root/shadowsocks/userapiconfig.py && \
    sed -i "s|MU_SUFFIX = 'zhaoj.in'|MU_SUFFIX = '${MU_SUFFIX}'|"              /root/shadowsocks/userapiconfig.py && \
    sed -i "s|MU_REGEX = '%5m%id.%suffix'|MU_REGEX = '${MU_REGEX}'|"           /root/shadowsocks/userapiconfig.py && \
    sed -i "s|API_INTERFACE = 'modwebapi'|API_INTERFACE = '${API_INTERFACE}'|" /root/shadowsocks/userapiconfig.py && \
    sed -i "s|WEBAPI_URL = 'https://example.com'|WEBAPI_URL = '${WEBAPI_URL}'|"   /root/shadowsocks/userapiconfig.py && \
    sed -i "s|WEBAPI_TOKEN = 'example-key'|WEBAPI_TOKEN = '${WEBAPI_TOKEN}'|"       /root/shadowsocks/userapiconfig.py && \
    sed -i "s|DeviceOnlineMinTraffic = 10|DeviceOnlineMinTraffic = '${DeviceOnlineMinTraffic}'|"       /root/shadowsocks/userapiconfig.py && \
    sed -i "s|MYSQL_HOST = '127.0.0.1'|MYSQL_HOST = '${MYSQL_HOST}'|"          /root/shadowsocks/userapiconfig.py && \
    sed -i "s|MYSQL_PORT = 3306|MYSQL_PORT = ${MYSQL_PORT}|"                   /root/shadowsocks/userapiconfig.py && \
    sed -i "s|MYSQL_USER = 'ss'|MYSQL_USER = '${MYSQL_USER}'|"                 /root/shadowsocks/userapiconfig.py && \
    sed -i "s|MYSQL_PASS = 'ss'|MYSQL_PASS = '${MYSQL_PASS}'|"                 /root/shadowsocks/userapiconfig.py && \
    sed -i "s|MYSQL_DB = 'shadowsocks'|MYSQL_DB = '${MYSQL_DB}'|"              /root/shadowsocks/userapiconfig.py && \
    sed -i "s|\"redirect\": \"\"|\"redirect\": \"${REDIRECT}\"|"               /root/shadowsocks/user-config.json && \
    sed -i "s|\"fast_open\": false|\"fast_open\": ${FAST_OPEN}|"               /root/shadowsocks/user-config.json && \
    sed -i "s|\"out_bind\": \"\"|\"out_bind\":\"0.0.0.0\"|"		       /root/shadowsocks/user-config.json && \
    echo -e "${DNS_1}\n${DNS_2}\n" >                                           /root/shadowsocks/dns.conf         && \
    python /root/shadowsocks/server.py