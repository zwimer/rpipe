FROM python:3.13-alpine

RUN pip install -U pip
COPY . /src

RUN apk add gcc python3-dev musl-dev linux-headers \
 && pip install /src \
 && apk add gcc python3-dev musl-dev linux-headers

RUN addgroup rpipe -g 1000
RUN adduser -u 1000 -HD rpipe -G rpipe
USER rpipe
