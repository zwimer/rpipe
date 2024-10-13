FROM python:3.12-alpine3.20

COPY . /app
WORKDIR /app

RUN pip install -U pip
RUN pip install rpipe
