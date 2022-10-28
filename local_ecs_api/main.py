import logging
import os
import sys

import requests
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import Response

from local_ecs_api.models import (
    DescribeTasksRequest,
    DescribeTasksResponse,
    ECSBackend,
    ListTasksRequest,
    ListTasksResponse,
    RunTaskRequest,
    RunTaskResponse,
)

log = logging.getLogger("local-ecs-api")
log.setLevel(logging.DEBUG)
stream = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(levelname)s:     %(message)s")
stream.setFormatter(formatter)
log.addHandler(stream)

app = FastAPI()
backend = ECSBackend()


@app.middleware("http")
async def add_resource_path(request: Request, call_next):
    """Parses the endpoint path from the request header and replaces the original resource path"""
    request.scope["path"] = "/" + request.headers.get("x-amz-target", "").split(".")[-1]
    response = await call_next(request)
    return response


@app.post("/ListTasks", response_model=ListTasksResponse)
async def list_tasks(request: Request) -> ListTasksResponse:
    """Retreives the local docker task ARNs that meet the request filters"""
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
    """Retreives the local docker tasks for the specified Task ARNs"""
    request_json = await request.json()
    request = DescribeTasksRequest(**request_json)

    output = backend.describe_tasks(tasks=request.tasks, include=request.include)
    return DescribeTasksResponse(**output)


@app.post("/RunTask", response_model=RunTaskResponse)
async def run_task(request: Request) -> RunTaskResponse:
    """Runs workflow to execute ECS task within local docker environment"""
    request_json = await request.json()
    request = RunTaskRequest(**request_json)

    output = backend.run_task(**request.dict(exclude_none=True))
    return RunTaskResponse(**output)


@app.post("/{full_path:path}")
async def redirect(request: Request, full_path: str):
    """Redirect request to endpoint specified witin ECS_ENDPOINT_URL environment variable"""
    redirect_url = os.environ.get("ECS_ENDPOINT_URL", "https://ecs.amazonaws.com")
    log.info("Redirecting path: %s to: %s", request.scope["path"], redirect_url)

    # AWS service APIs require resource path to be "/"
    request.scope["path"] = "/"
    data = await request.json()

    if request.method == "POST":
        response = requests.post(
            os.environ.get("ECS_ENDPOINT_URL", "https://ecs.amazonaws.com"),
            headers=dict(request.headers.items()),
            json=data,
            timeout=10,
        )

    elif request.method == "GET":
        response = requests.get(
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
