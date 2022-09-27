FROM python:3.9-slim-buster
LABEL maintainer="Marshall Mamiya"
# COPY LICENSE /app
WORKDIR /app

COPY ./install.sh /app/install.sh
COPY ./pyproject.toml /app/pyproject.toml
RUN bash ./install.sh && pip install .

COPY ./local_ecs_api /app/local_ecs_api
RUN pip install .

CMD ["python", "/app/local_ecs_api/main.py"] 