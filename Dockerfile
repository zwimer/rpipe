FROM python:3.14-alpine

RUN adduser -D user
USER user

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="$PATH:/home/user/.local/bin"

COPY --chown=user:user\
    pyproject.toml \
    README.md \
    LICENSE \
    /rpipe/
COPY --chown=user:user rpipe/ /rpipe/rpipe/

RUN pip install --user --no-cache-dir /rpipe
ENTRYPOINT ["rpipe_server"]
