from typing import Any, Dict, List, Optional

import pickle

from fastapi import FastAPI, APIRouter
from starlette.requests import Request
from starlette.responses import JSONResponse

from local_ecs_api.exceptions import EcsAPIException
from local_ecs_api.models import (
    RunTaskRequest,
    RunTaskResponse,
    DescribeTasksRequest,
    DescribeTasksResponse,
    ListTasksRequest,
    ECSBackend,
    RunTaskBackend,
)
import os
import logging
from pprint import pformat

log = logging.getLogger(__file__)
log.setLevel(logging.DEBUG)

BACKEND_PATH = os.path.join(os.path.dirname(__file__), ".backend.pickle")

app = FastAPI()


try:
    with open(BACKEND_PATH, "rb") as f:
        backend = pickle.load(f)
except Exception:
    backend = ECSBackend(BACKEND_PATH)


@app.post("/ListTasks", response_model=RunTaskResponse)
def list_tasks(request: ListTasksRequest) -> None:
    return backend.list_tasks(request)


@app.post("/DescribeTasks")
def describe_tasks(request: DescribeTasksRequest) -> DescribeTasksResponse:
    output = backend.describe_tasks(request.tasks, include=request.include)
    return DescribeTasksResponse(**output)


@app.post("/RunTask", response_model=RunTaskResponse)
def run_task(request: RunTaskRequest) -> RunTaskResponse:
    docker_task = backend.run_task(
        request.taskDefinition, request.overrides, request.count
    )

    backend.tasks[docker_task.id] = RunTaskBackend(request, docker_task)
    output = backend.describe_tasks([docker_task.id])
    log.debug(pformat(output))
    return RunTaskResponse(**output)


@app.exception_handler(EcsAPIException)
async def ecs_api_exception_handler(_: Request, exc: EcsAPIException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content={"message": exc.message, "code": exc.code}
    )


if __name__ == "__main__":
    from uvicorn import run

    run(app=app, port=8080)
