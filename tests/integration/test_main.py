import logging
import uuid
from pprint import pformat

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_ecs, mock_secretsmanager, mock_ssm, mock_sts
from python_on_whales import docker

from local_ecs_api.main import app
from tests.data import task_defs

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

client = TestClient(app)


@mock_ecs
@mock_sts
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
@mock_sts
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
    assert len(response_json["tasks"][0]["containers"]) == len(
        task["taskDefinition"]["containerDefinitions"]
    )


@pytest.mark.usefixtures("aws_credentials")
@mock_ecs
@mock_sts
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
@mock_sts
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
@mock_sts
def test_run_task_with_overrides():
    """
    Ensures RunTask endpoint returns the expected response for requests with overrides
    """
    ecs = boto3.client("ecs")
    task = ecs.register_task_definition(**task_defs["fast_success"])

    override_env = {"foo": "new"}
    override_task_role = "arn:aws:iam::12345679012:role/new"

    response = client.post(
        "/",
        headers={"x-amz-target": "RunTask"},
        json={
            "taskDefinition": task["taskDefinition"]["taskDefinitionArn"],
            "overrides": {
                "containerOverrides": [
                    {
                        "name": task_defs["fast_success"]["containerDefinitions"][0][
                            "name"
                        ],
                        "environment": [
                            {"name": key, "value": value}
                            for key, value in override_env.items()
                        ],
                    }
                ],
                "taskRoleArn": override_task_role,
            },
        },
    )
    response_data = response.json()

    log.info("Assert override environment variables are present in task container")
    actual_env = {}
    container_id = response_data["tasks"][0]["containers"][0]["runtimeId"]
    for env in docker.container.inspect(container_id).config.env:
        env = env.split("=")
        actual_env.update({env[0]: env[1]})

    # assert override env dict is a subset of the actual env dict
    assert override_env.items() <= actual_env.items()

    log.info("Assert override task role is present in task container")
    assert (
        actual_env.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
        == "/role/" + override_task_role.rsplit("/", maxsplit=1)[-1]
    )


@pytest.mark.usefixtures("aws_credentials")
@mock_ecs
@mock_sts
def test_run_task_with_network_configuration():
    """
    Ensures RunTask endpoint returns the expected response for task definitions
    that are expected to fail
    """
    ecs = boto3.client("ecs")
    task = ecs.register_task_definition(**task_defs["fast_success"])

    response = client.post(
        "/",
        headers={"x-amz-target": "RunTask"},
        json={
            "taskDefinition": task["taskDefinition"]["taskDefinitionArn"],
            "networkConfiguration": {
                "awsvpcConfiguration": {
                    "assignPublicIp": "DISABLED",
                    "subnets": ["subnet-123"],
                    "securityGroups": ["sg-123"],
                }
            },
        },
    )
    assert response.status_code == 200


@pytest.mark.usefixtures("aws_credentials")
@mock_ecs
@mock_sts
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

    response_data = response.json()
    log.debug("Response:")
    log.debug(pformat(response_data))

    assert len(response_data["failures"]) == 0

    assert response_data["tasks"][0]["stopCode"] == 18
    assert response_data["tasks"][0]["lastStatus"] == "STOPPED"


@pytest.mark.usefixtures("aws_credentials")
@mock_ecs
@mock_secretsmanager
@mock_ssm
@mock_sts
def test_run_task_with_secrets():
    """
    Ensures RunTask endpoint returns the expected response for task definitions
    that contain secrets and decrypted secrets are passed to container
    """
    ecs = boto3.client("ecs")
    ssm = boto3.client("ssm")
    secret_manager = boto3.client("secretsmanager")

    ssm_secret = "ssm-secret"
    secret_manager_secret = "secret-manager-secret"

    task_def = task_defs["fast_success"].copy()
    ssm_key = f"secret-{uuid.uuid4()}"

    # create mock SSM parameter store and Secret Manager secret
    ssm.put_parameter(Name=ssm_key, Type="SecureString", Value=ssm_secret)
    ssm_arn = ssm.get_parameter(Name=ssm_key)["Parameter"]["ARN"]

    secret_manager_arn = secret_manager.create_secret(
        Name=f"secret-{uuid.uuid4()}",
        SecretString=secret_manager_secret,
    )["ARN"]

    task_def["containerDefinitions"][0]["secrets"] = [
        {"name": "SSM_SECRET", "valueFrom": ssm_arn},
        {"name": "SECRET_MANAGER_SECRET", "valueFrom": secret_manager_arn},
    ]
    task = ecs.register_task_definition(**task_def)

    response = client.post(
        "/",
        headers={"x-amz-target": "RunTask"},
        json={"taskDefinition": task["taskDefinition"]["taskDefinitionArn"]},
    )
    assert response.status_code == 200

    response_data = response.json()
    log.debug("Response:")
    log.debug(pformat(response_data))

    assert len(response_data["failures"]) == 0

    # run inspect on container and returns list of str env vars
    container_id = response_data["tasks"][0]["containers"][0]["runtimeId"]
    container_env_vars = docker.container.inspect(container_id).config.env

    assert f"SSM_SECRET={ssm_secret}" in container_env_vars
    assert f"SECRET_MANAGER_SECRET={secret_manager_secret}" in container_env_vars
