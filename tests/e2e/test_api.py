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

from local_ecs_api.converters import ECS_NETWORK_NAME, DOCKER_PROJECT_PREFIX
from tests.data import task_defs

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

FILE_DIR = os.path.dirname(__file__)


# test the potential ways users may pass AWS credentials to the local-ecs-api container
@pytest.fixture(
    scope="module",
    autouse=True,
    params=[
        [os.path.join(FILE_DIR, "docker-compose.creds-env-vars.yml")],
        [os.path.join(FILE_DIR, "docker-compose.creds-volume.yml")],
    ],
    ids=["aws-creds-env-vars", "aws-creds-volume"],
)
def local_api(request) -> DockerClient:
    """Creates local-ecs-api compose project"""
    if os.environ.get("IS_DEV_CONTAINER") and not os.environ.get("AWS_CREDS_HOST_PATH"):
        # reason being that the ~/.aws host path will differ between local machines and
        # setting the host path to the dev container's absolute path results in a mounting
        # permission error (atleast for MacOS)
        pytest.fail(
            "AWS_CREDS_HOST_PATH needs to be explicitly set if running tests within docker container"
        )
    else:
        os.environ["AWS_CREDS_HOST_PATH"] = os.path.join(FILE_DIR, "mock-aws-creds")

    # docker network to host local-ecs-api compose project
    os.environ["NETWORK_NAME"] = "local-ecs-api-tests"

    compose_files = [os.path.join(FILE_DIR, "docker-compose.yml")] + request.param
    client = DockerClient(compose_files=compose_files)

    client.compose.up(build=True, detach=True, quiet=True)

    yield docker

    log.debug("Disconnecting containers from network: %s", ECS_NETWORK_NAME)
    try:
        containers = list(client.network.inspect(ECS_NETWORK_NAME).containers.keys())
    except DockerException as err:
        if re.search(r"Error: No such network:", err.stderr):
            log.debug("Network does not exists -- skipping")
        else:
            raise err
    else:
        log.debug(pformat(containers))

        client.container.remove(containers, force=True, volumes=True)
        client.network.remove(ECS_NETWORK_NAME)

    client.compose.stop()
    # keeps local-ecs-api compose project containers to access
    # docker logs for debugging if any test(s) failed
    if not getattr(request.node.obj, "any_failures", False):
        client.compose.down(volumes=True)
        # TODO: create teardown logic to remove ONLY task containers
        # that are dangling
        # maybe use a filter on docker label?
        # or use DOCKER_PROJECT_PREFIX to filter out unrelated projects


@pytest.fixture(scope="module", autouse=True)
def connect_tests_to_api(local_api) -> None:
    """Connects dev container (if used) to docker network associated with ECS tasks"""
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
    """Ensures RunTask endpoint is successful from the AWS SDK"""
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    task = ecs.register_task_definition(**task_defs["fast_success"])

    response = ecs.run_task(
        taskDefinition=task["taskDefinition"]["taskDefinitionArn"],
    )
    log.debug("Response:")
    log.debug(pformat(response))


@pytest.fixture
def mock_task_role_arn() -> str:
    """
    Creates a mock ECS task role that the ECS endpoint will use to vend
    credentials to task containers
    """
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
    """Ensures task container is given AWS credentials to perform it's operation"""
    task_def = task_defs["aws_call"].copy()
    task_def["taskRoleArn"] = mock_task_role_arn

    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    task = ecs.register_task_definition(**task_def)
    response = ecs.run_task(
        taskDefinition=task["taskDefinition"]["taskDefinitionArn"],
    )
    log.debug("Response:")
    log.debug(pformat(response))

    # TODO: create assertion to check if task container exited without error


@pytest.mark.usefixtures("aws_credentials")
def test_multiple_run_task_calls(mock_task_role_arn):
    """
    Ensures subsequent RunTask calls don't fail and that a new docker project
    is created for each call
    """
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    task = ecs.register_task_definition(**task_defs["fast_success"])

    expected_project_names = []
    for _ in range(3):
        response = ecs.run_task(
            taskDefinition=task["taskDefinition"]["taskDefinitionArn"],
        )
        log.debug("Response:")
        log.debug(pformat(response))

        assert len(response["failures"]) == 0

        expected_project_names.append(
            DOCKER_PROJECT_PREFIX + response["tasks"][0]["taskArn"].split("/")[-1]
        )

    all_project_names = [proj.name for proj in docker.compose.ls(all=True)]
    log.debug("All docker project names:")
    log.debug(pformat(all_project_names))

    log.info("Assert that a separate docker project is created for each RunTask call")
    for name in expected_project_names:
        assert name in all_project_names


@pytest.mark.usefixtures("aws_credentials")
def test_describe_tasks():
    """Ensures DescribeTasks endpoint is successful from the AWS SDK"""
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    response = ecs.describe_tasks(tasks=[])
    log.debug("Response:")
    log.debug(pformat(response))


@pytest.mark.usefixtures("aws_credentials")
def test_list_tasks():
    """Ensures LisTasks endpoint is successful from the AWS SDK"""
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    response = ecs.list_tasks()
    log.debug("Response:")
    log.debug(pformat(response))
