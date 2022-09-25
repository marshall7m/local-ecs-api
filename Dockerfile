FROM python:3.9-slim-buster
LABEL maintainer="Marshall Mamiya"
# COPY LICENSE /app
WORKDIR /app

COPY ./pyproject.toml /app/pyproject.toml
RUN pip install .

COPY ./local_ecs_api /app/local_ecs_api
RUN pip install .

CMD ["python", "/app/local_ecs_api/main.py"] 