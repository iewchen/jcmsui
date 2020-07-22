FROM python:3.7-slim-buster
LABEL maintainer="Wei Chen <chenw1@uthscsa.edu"

# install latex
RUN set -x \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      texlive-latex-recommended \
 && rm -fr /var/cache/apt/* /var/lib/apt/lists/*

ADD . /var/webapp/jcmsui
COPY config.toml.example /var/webapp/jcmsui/config.toml
WORKDIR /var/webapp/jcmsui

RUN pip install -r requirements.txt


EXPOSE 7001

CMD python jcmsui.py
