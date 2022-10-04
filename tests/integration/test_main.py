from fastapi.testclient import TestClient
from moto import mock_ecs
import boto3
from local_ecs_api.main import app
from tests.data import task_defs

client = TestClient(app)


@mock_ecs
def test_list_tasks(aws_credentials):
    ecs = boto3.client("ecs")
    cluster = "test-cluster"
    task = ecs.register_task_definition("")

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

    # TODO: create proper expected response
    assert response_json == {
        "failures": [],
        "tasks": [],
    }


@mock_ecs
def test_run_task_with_success(aws_credentials):
    ecs = boto3.client("ecs")
    task = ecs.register_task_definition(**task_defs["fast_success"])

    response = client.post(
        "/",
        headers={"x-amz-target": "RunTask"},
        json={"taskDefinition": task["taskDefinition"]["taskDefinitionArn"]},
    )
    assert response.status_code == 200


@mock_ecs
def test_run_task_with_failure(aws_credentials):
    ecs = boto3.client("ecs")
    task = ecs.register_task_definition(**task_defs["fast_fail"])

    response = client.post(
        "/",
        headers={"x-amz-target": "RunTask"},
        json={"taskDefinition": task["taskDefinition"]["taskDefinitionArn"]},
    )
    assert response.status_code == 200
