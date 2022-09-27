import pytest
from fastapi.testclient import TestClient
from local_ecs_api.main import app
from moto import mock_ecs
import boto3
import os

client = TestClient(app)


@mock_ecs
def test_list_tasks():
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

    run_task = client.post(
        "/RunTask",
        json={
            "taskDefinition": task["taskDefinition"]["taskDefinitionArn"],
            "cluster": "test-cluster",
            "launchType": "FARGATE",
            "startedBy": "tester",
        },
    ).json()["tasks"][0]

    response = client.post(
        "/ListTasks",
        json={
            "cluster": run_task["clusterArn"],
            "family": "test",
            "launchType": run_task["launchType"],
            "serviceName": task["taskDefinition"]["containerDefinition"][0]["name"],
            "startedBy": task["startedBy"],
            "desiredStatus": "STOPPED",
        },
    ).json()

    assert run_task["taskArn"] in response["taskArns"]


@mock_ecs
def test_describe_tasks():
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
def test_run_task(aws_credentials):
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
