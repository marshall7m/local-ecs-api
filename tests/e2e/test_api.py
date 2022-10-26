import os
import logging
import re
from pprint import pformat
import json
import uuid

import pytest
import boto3
from python_on_whales import DockerClient, docker
from python_on_whales.exceptions import DockerException

from local_ecs_api.converters import ECS_NETWORK_NAME
from tests.data import task_defs

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

FILE_DIR = os.path.dirname(__file__)


@pytest.fixture(
    scope="module",
    autouse=True,
    params=[
        [os.path.join(FILE_DIR, "docker-compose.creds-env-vars.yml")],
        [os.path.join(FILE_DIR, "docker-compose.creds-volume.yml")],
    ],
    ids=["aws-creds-env-vars", "aws-creds-volume"],
)
def local_api(request):
    if os.environ.get("IS_DEV_CONTAINER") and not os.environ.get("AWS_CREDS_HOST_PATH"):
        pytest.fail(
            "AWS_CREDS_HOST_PATH needs to be explicitly set if running tests within docker container"
        )

    os.environ["NETWORK_NAME"] = "local-ecs-api-tests"

    compose_files = [os.path.join(FILE_DIR, "docker-compose.yml")] + request.param
    client = DockerClient(compose_files=compose_files)

    client.compose.up(build=True, detach=True, quiet=True)

    yield docker

    containers = list(client.network.inspect(ECS_NETWORK_NAME).containers.keys())
    log.debug(pformat(containers))

    client.container.remove(containers, force=True, volumes=True)
    client.network.remove(ECS_NETWORK_NAME)

    client.compose.stop()
    if not getattr(request.node.obj, "any_failures", False):
        client.compose.down(volumes=True)


@pytest.fixture(scope="module", autouse=True)
def connect_tests_to_api(local_api):
    # CI env var will be set if running in GitHub Action job
    if not os.environ.get("CI"):
        os.environ["LOCAL_ECS_API_ENDPOINT"] = "http://local-ecs-api:8000"
        # needed only if running tests within container
        log.debug("Connecting dev container to API network")
        with open("/etc/hostname", "r", encoding="utf-8") as f:
            container_id = f.read().strip()
            try:
                docker.network.connect(os.environ["NETWORK_NAME"], container_id)
            except DockerException as err:
                if re.search(r"already exists in network", err.stderr):
                    log.debug("Container is already associated")
                else:
                    raise err

        yield

        docker.network.disconnect(os.environ["NETWORK_NAME"], container_id)
    else:
        os.environ["LOCAL_ECS_API_ENDPOINT"] = "http://localhost:8000"
        yield


@pytest.mark.usefixtures("aws_credentials")
def test_redirect_supported():
    """Ensures ECS API requests that aren't covered by local API are redirected to target AWS ECS endpoint"""
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    response = ecs.list_clusters()

    assert "clusterArns" in response


@pytest.mark.usefixtures("aws_credentials")
def test_run_task():
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    task = ecs.register_task_definition(**task_defs["fast_success"])
    response = ecs.run_task(
        taskDefinition=task["taskDefinition"]["taskDefinitionArn"],
    )
    log.debug("Response:")
    log.debug(pformat(response))


@pytest.fixture
def mock_task_role_arn():
    iam = boto3.client("iam", endpoint_url="http://moto:5000")
    res = iam.create_role(
        RoleName="task-role-" + str(uuid.uuid4()),
        AssumeRolePolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "sts:AssumeRole",
                        "Principal": {"AWS": "123456789012"},
                    }
                ],
            }
        ),
    )

    yield res["Role"]["Arn"]

    iam.delete_role(RoleName=res["Role"]["RoleName"])


@pytest.mark.usefixtures("aws_credentials")
def test_run_task_aws_call(mock_task_role_arn):
    task_def = task_defs["aws_call"].copy()
    task_def["taskRoleArn"] = mock_task_role_arn

    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    task = ecs.register_task_definition(**task_def)

    response = ecs.run_task(
        taskDefinition=task["taskDefinition"]["taskDefinitionArn"],
    )
    log.debug("Response:")
    log.debug(pformat(response))


@pytest.mark.usefixtures("aws_credentials")
def test_describe_tasks():
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    response = ecs.describe_tasks(tasks=[])
    log.debug("Response:")
    log.debug(pformat(response))


@pytest.mark.usefixtures("aws_credentials")
def test_list_tasks():
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    response = ecs.list_tasks()
    log.debug("Response:")
    log.debug(pformat(response))
