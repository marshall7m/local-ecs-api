FROM tiangolo/uvicorn-gunicorn:python3.9
LABEL maintainer="Marshall Mamiya"
# COPY LICENSE /app
WORKDIR /app
EXPOSE 8000
COPY ./install.sh /app/install.sh
COPY ./pyproject.toml /app/pyproject.toml
RUN bash ./install.sh && pip install .

COPY ./local_ecs_api /app/local_ecs_api
RUN pip install .

CMD ["python", "/app/local_ecs_api/main.py"] 