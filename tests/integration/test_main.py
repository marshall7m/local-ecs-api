import os
import uuid

import pytest
from fastapi.testclient import TestClient
from moto import mock_ecs
import boto3

from local_ecs_api.main import app

client = TestClient(app)

task_def = {
    "fast_fail": {
        "containerDefinitions": [
            {
                "name": "exit",
                "command": [
                    "/bin/sh",
                    "fail",
                ],
                "cpu": 1,
                "essential": True,
                "image": "busybox",
                "memory": 10,
            }
        ],
        "family": "fast_fail",
        "taskRoleArn": "arn:aws:iam::12345679012:role/mock-task",
    },
    "essential_success": {
        "containerDefinitions": [
            {
                "name": "sleep",
                "command": [
                    "sleep",
                    "5",
                ],
                "cpu": 10,
                "essential": True,
                "image": "busybox",
                "memory": 10,
            },
        ],
        "family": "essential_success",
        "taskRoleArn": "arn:aws:iam::12345679012:role/mock-task",
    },
    "fast_success": {
        "containerDefinitions": [
            {
                "name": "shell",
                "command": ["/bin/bash"],
                "cpu": 1,
                "essential": True,
                "image": "busybox",
                "memory": 10,
            },
        ],
        "family": "fast_success",
        "taskRoleArn": "arn:aws:iam::12345679012:role/mock-task",
    },
    "invalid_img": {
        "containerDefinitions": [
            {
                "name": "shell",
                "command": ["/bin/bash"],
                "cpu": 1,
                "essential": True,
                "image": f"invalid:{uuid.uuid4()}",
                "memory": 10,
            },
        ],
        "family": "invalid_img",
        "taskRoleArn": "arn:aws:iam::12345679012:role/mock-task",
    },
}


@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@mock_ecs
def test_list_tasks(aws_credentials):
    ecs = boto3.client("ecs")
    cluster = "test-cluster"
    task = ecs.register_task_definition("")

    run_task = client.post(
        "/RunTask",
        json={
            "taskDefinition": task["taskDefinition"]["taskDefinitionArn"],
            "cluster": cluster,
            "launchType": "FARGATE",
            "startedBy": "tester",
        },
    ).json()["tasks"][0]

    response = client.post(
        "/ListTasks",
        json={
            "cluster": cluster,
            "family": task["taskDefinition"]["family"],
            "launchType": run_task["launchType"],
            "serviceName": run_task["containers"][0]["name"],
            "startedBy": run_task["startedBy"],
            "desiredStatus": "STOPPED",
        },
    ).json()

    assert run_task["taskArn"] in response["taskArns"]


@mock_ecs
def test_describe_tasks(aws_credentials):
    ecs = boto3.client("ecs")
    task = ecs.register_task_definition(
        containerDefinitions=[
            {
                "name": "sleep",
                "command": [
                    "sleep",
                    "5",
                ],
                "cpu": 10,
                "essential": True,
                "image": "busybox",
                "memory": 10,
            },
        ],
        family="sleep5",
        taskRoleArn="arn:aws:iam::12345679012:role/mock-task",
    )

    task_arn = client.post(
        "/RunTask", json={"taskDefinition": task["taskDefinition"]["taskDefinitionArn"]}
    ).json()["tasks"][0]["taskArn"]

    response = client.post("/DescribeTasks", json={"tasks": [task_arn]})
    assert response.status_code == 200
    response_json = response.json()

    # TODO: create proper expected response
    assert response_json == {
        "failures": [],
        "tasks": [],
    }


@mock_ecs
def test_run_task_with_failure(aws_credentials):
    ecs = boto3.client("ecs")
    task = ecs.register_task_definition(**task_def["fast_fail"])

    response = client.post(
        "/RunTask", json={"taskDefinition": task["taskDefinition"]["taskDefinitionArn"]}
    )
    assert response.status_code == 200
    response_json = response.json()

    # TODO: create proper expected response
    assert response_json == {
        "failures": [],
        "tasks": [],
    }
