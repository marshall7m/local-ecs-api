FROM python:3.9-slim-buster
LABEL maintainer="Marshall Mamiya"
WORKDIR /app
EXPOSE 8000
COPY ./LICENSE /app
COPY ./install.sh /app/install.sh
COPY ./pyproject.toml /app/pyproject.toml
RUN bash ./install.sh

COPY ./local_ecs_api /app/local_ecs_api
RUN pip install -e .

CMD ["python", "/app/local_ecs_api/main.py"] 