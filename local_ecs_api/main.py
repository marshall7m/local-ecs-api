from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse

from local_ecs_api.exceptions import EcsAPIException
from local_ecs_api.converters import get_docker_compose_stack, get_compose_failures
from local_ecs_api.models import (
    RunTaskRequest,
    RunTaskResponse,
    DescribeTasksRequest,
    ListTasksRequest
)
import logging

log = logging.getLogger(__file__)
log.setLevel(logging.DEBUG)

app = FastAPI()

@app.post("/ListTasks")
def list_tasks(request: ListTasksRequest) -> None:
    raise NotImplementedError

@app.post("/DescribeTasks")
def describe_tasks(request: DescribeTasksRequest) -> None:
    raise NotImplementedError


@app.post("/RunTask", response_model=RunTaskResponse)
def run_task(request: RunTaskRequest) -> RunTaskResponse:
    docker = get_docker_compose_stack(request)
    log.info("Running docker compose up")
    for i in range(request.count):
        log.debug(f"Count: {i+1}/{request.count}")
        docker.compose.up(
            build=True,
            detach=True,
            log_prefix=False
        )

    return RunTaskResponse(
        failures=get_compose_failures(docker),
        tasks=[]
    )


@app.exception_handler(EcsAPIException)
async def ecs_api_exception_handler(_: Request, exc: EcsAPIException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content={"message": exc.message, "code": exc.code}
    )


if __name__ == '__main__':
    from uvicorn import run

    run(app=app, port=8080)