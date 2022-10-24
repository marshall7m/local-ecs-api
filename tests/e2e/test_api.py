import os
import logging
import re
from pprint import pformat

import pytest
import boto3
from python_on_whales import DockerClient, docker
from python_on_whales.exceptions import DockerException, NoSuchVolume

from local_ecs_api.converters import ECS_NETWORK_NAME
from tests.data import task_defs

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

FILE_DIR = os.path.dirname(__file__)


@pytest.fixture(
    scope="module",
    autouse=True,
    params=[
        {
            "ECS_ENDPOINT_AWS_ACCESS_KEY_ID": "mock-aws-creds",
            "ECS_ENDPOINT_AWS_REGION": "us-west-2",
            "ECS_ENDPOINT_AWS_SECRET_ACCESS_KEY": "mock-aws-creds",
        },
        {
            "ECS_ENDPOINT_AWS_PROFILE": "test",
            "ECS_ENDPOINT_AWS_CREDS_HOST_PATH": os.path.join(
                os.path.dirname(__file__), "mock_aws_creds"
            ),
            "ECS_AWS_CREDS_VOLUME_NAME": "test-ecs-endpoint-aws-creds",
        },
    ],
    ids=["env_var_creds", "volume_creds"],
)
def compose_env_vars(request):
    _environ = os.environ.copy()
    for k, v in request.param.items():
        os.environ[k] = v

    yield request.param

    os.environ.clear()
    os.environ.update(_environ)


@pytest.fixture(scope="module", autouse=True)
def local_api(request, compose_env_vars):

    os.environ["NETWORK_NAME"] = "local-ecs-api-tests"

    client = DockerClient(compose_files=[os.path.join(FILE_DIR, "docker-compose.yml")])

    client.compose.up(build=True, detach=True, quiet=True)

    yield docker

    client.compose.stop()

    if not getattr(request.node.obj, "any_failures", False):
        client.compose.down()

    if os.environ.get("ECS_AWS_CREDS_VOLUME_NAME"):
        try:
            client.volume.remove(os.environ.get("ECS_AWS_CREDS_VOLUME_NAME"))
        except NoSuchVolume:
            log.debug(
                "Volume does not exist: %s", os.environ.get("ECS_AWS_CREDS_VOLUME_NAME")
            )

    containers = list(client.network.inspect(ECS_NETWORK_NAME).containers.keys())
    log.debug(pformat(containers))

    client.container.remove(containers, force=True, volumes=True)
    client.network.remove(ECS_NETWORK_NAME)


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
def test_run_task_success():
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    task = ecs.register_task_definition(**task_defs["fast_success"])
    response = ecs.run_task(
        taskDefinition=task["taskDefinition"]["taskDefinitionArn"],
    )
    log.debug("Response:")
    log.debug(pformat(response))

    if os.environ.get("ECS_AWS_CREDS_VOLUME_NAME"):
        log.info("Assert AWS creds volume exists after RunTask call")
        assert docker.volume.exists(os.environ["ECS_AWS_CREDS_VOLUME_NAME"]) is True


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
