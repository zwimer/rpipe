FROM python:3.13-alpine

RUN pip install -U pip
COPY . /src
RUN pip install /src

RUN addgroup rpipe -g 1000
RUN adduser -u 1000 -HD rpipe -G rpipe
USER rpipe
