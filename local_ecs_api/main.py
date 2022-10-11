import pickle
import sys
import os
import logging

import requests
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import Response

from local_ecs_api.models import (
    RunTaskRequest,
    RunTaskResponse,
    DescribeTasksRequest,
    DescribeTasksResponse,
    ListTasksRequest,
    ListTasksResponse,
    ECSBackend,
)

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
stream = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(levelname)s:     %(message)s")
stream.setFormatter(formatter)
log.addHandler(stream)

BACKEND_PATH = os.path.join(os.path.dirname(__file__), ".backend.pickle")

app = FastAPI()


try:
    with open(BACKEND_PATH, "rb") as f:
        backend = pickle.load(f)
except FileNotFoundError:
    backend = ECSBackend(BACKEND_PATH)


@app.middleware("http")
async def add_resource_path(request: Request, call_next):
    request.scope["path"] = "/" + request.headers.get("x-amz-target", "").split(".")[-1]
    response = await call_next(request)
    return response


@app.post("/ListTasks", response_model=ListTasksResponse)
async def list_tasks(request: Request) -> ListTasksResponse:
    request_json = await request.json()
    request = ListTasksRequest(**request_json)

    arns = backend.list_tasks(
        cluster=request.cluster,
        family=request.family,
        launch_type=request.launchType,
        service_name=request.serviceName,
        desired_status=request.desiredStatus,
        started_by=request.startedBy,
        container_instance=request.containerInstance,
        max_results=request.maxResults,
    )
    return ListTasksResponse(taskArns=arns)


@app.post("/DescribeTasks", response_model=DescribeTasksResponse)
async def describe_tasks(request: Request) -> DescribeTasksResponse:
    request_json = await request.json()
    request = DescribeTasksRequest(**request_json)

    output = backend.describe_tasks(tasks=request.tasks, include=request.include)
    return DescribeTasksResponse(**output)


@app.post("/RunTask", response_model=RunTaskResponse)
async def run_task(request: Request) -> RunTaskResponse:
    request_json = await request.json()
    request = RunTaskRequest(**request_json)

    output = backend.run_task(**request.dict(exclude_none=True))
    return RunTaskResponse(**output)


@app.post("/{full_path:path}")
async def redirect(request: Request, full_path: str):
    """Redirect request to endpoint specified witin $ECS_ENDPOINT_URL"""
    request.scope["path"] = "/"
    data = await request.json()

    response = requests.post(
        os.environ.get("ECS_ENDPOINT_URL", "https://ecs.amazonaws.com"),
        headers=dict(request.headers.items()),
        json=data,
        timeout=10,
    )

    # translates requests.models.Response to starlette.responses.Response
    return Response(
        status_code=response.status_code,
        content=response.content,
        headers=response.headers,
        media_type=response.headers["Content-Type"],
    )


if __name__ == "__main__":
    from uvicorn import run

    run(app=app, port=8000, host="0.0.0.0")
