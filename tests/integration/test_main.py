import pytest
from fastapi.testclient import TestClient
from local_ecs_api.main import app
from moto import mock_ecs
import boto3
import os

client = TestClient(app)


@pytest.mark.skip("Not implemented")
def test_list_tasks():
    pass


@pytest.mark.skip("Not implemented")
def test_describe_tasks():
    pass


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
    print(response.text)
    assert response.status_code == 200
    response_json = response.json()
    assert response_json == {
        "failures": [],
        "tasks": [],
    }
