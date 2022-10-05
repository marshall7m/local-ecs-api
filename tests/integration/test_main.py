import logging
from pprint import pformat

import pytest
from fastapi.testclient import TestClient
from moto import mock_ecs
import boto3
from local_ecs_api.main import app
from tests.data import task_defs

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

client = TestClient(app)


@mock_ecs
def test_list_tasks(aws_credentials):
    """
    Ensures ListTask endpoint returns the expected list of task ARNs
    """
    ecs = boto3.client("ecs")
    cluster = "test-cluster"
    task = ecs.register_task_definition(**task_defs["fast_success"])

    run_task = client.post(
        "/",
        headers={"x-amz-target": "RunTask"},
        json={
            "taskDefinition": task["taskDefinition"]["taskDefinitionArn"],
            "cluster": cluster,
            "launchType": "FARGATE",
            "startedBy": "tester",
        },
    ).json()["tasks"][0]

    response = client.post(
        "/",
        headers={"x-amz-target": "ListTasks"},
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
def test_describe_tasks_gets_updated_results(aws_credentials):
    """
    Ensures DescribeTasks endpoint returns the expected response for filtering
    task that are expected to succeed
    """
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
        "/",
        headers={"x-amz-target": "RunTask"},
        json={"taskDefinition": task["taskDefinition"]["taskDefinitionArn"]},
    ).json()["tasks"][0]["taskArn"]

    response = client.post(
        "/", headers={"x-amz-target": "DescribeTasks"}, json={"tasks": [task_arn]}
    )
    assert response.status_code == 200
    response_json = response.json()

    assert len(response_json["failures"]) == 0
    assert len(response_json["tasks"]["containers"]) == len(
        task["containerDefinitions"]
    )


@pytest.mark.usefixtures("aws_credentials")
@mock_ecs
def test_run_task_with_success():
    """
    Ensures RunTask endpoint returns the expected response for task definitions
    that are expected to succeed
    """
    ecs = boto3.client("ecs")
    task = ecs.register_task_definition(**task_defs["fast_success"])

    response = client.post(
        "/",
        headers={"x-amz-target": "RunTask"},
        json={"taskDefinition": task["taskDefinition"]["taskDefinitionArn"]},
    )
    assert response.status_code == 200

    data = response.json()
    log.debug("Response:")
    log.debug(pformat(data))

    assert len(data["failures"]) == 0
    assert len(data["tasks"][0]["containers"]) == len(
        task_defs["fast_success"]["containerDefinitions"]
    )

    for c in data["tasks"][0]["containers"]:
        assert c["lastStatus"] == "exited"


@pytest.mark.usefixtures("aws_credentials")
@mock_ecs
def test_run_task_with_failure():
    """
    Ensures RunTask endpoint returns the expected response for task definitions
    that are expected to fail
    """
    ecs = boto3.client("ecs")
    task = ecs.register_task_definition(**task_defs["fast_fail"])

    response = client.post(
        "/",
        headers={"x-amz-target": "RunTask"},
        json={"taskDefinition": task["taskDefinition"]["taskDefinitionArn"]},
    )
    assert response.status_code == 200

    data = response.json()
    log.debug("Response:")
    log.debug(pformat(data))

    assert len(data["failures"]) == 1


@pytest.mark.usefixtures("aws_credentials")
@mock_ecs
def test_run_task_pull_img_failure():
    """
    Ensures RunTask endpoint returns the expected response for task definitions
    that are expected to fail at the task setup level
    """
    ecs = boto3.client("ecs")
    task = ecs.register_task_definition(**task_defs["invalid_img"])

    response = client.post(
        "/",
        headers={"x-amz-target": "RunTask"},
        json={"taskDefinition": task["taskDefinition"]["taskDefinitionArn"]},
    )
    assert response.status_code == 200

    data = response.json()
    log.debug("Response:")
    log.debug(pformat(data))

    assert len(data["failures"]) == 0

    assert data["tasks"][0]["stopCode"] == "TaskFailedToStart"
    assert data["tasks"][0]["lastStatus"] == "STOPPED"
