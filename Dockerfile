FROM python:3.11-alpine3.17

COPY . /app
WORKDIR /app

RUN pip install -U pip
RUN pip install rpipe
