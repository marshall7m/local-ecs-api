import os
import logging
import re
import requests
from pprint import pformat

import pytest
import boto3
from python_on_whales import DockerClient
from python_on_whales.exceptions import DockerException

from tests.data import task_defs

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

FILE_DIR = os.path.dirname(__file__)


@pytest.fixture(scope="module", autouse=True)
def local_ecs_api():
    os.environ["NETWORK_NAME"] = "local-ecs-api-tests"
    # os.environ["LOCAL_ECS_API_ALIAS"] = "local-ecs"
    os.environ["LOCAL_ECS_API_ENDPOINT"] = "http://" + "local-ecs-api" + ":8000"
    docker = DockerClient(compose_files=[os.path.join(FILE_DIR, "docker-compose.yml")])

    docker.compose.up(build=True, detach=True)

    log.debug("Connecting testing container to API network")
    with open("/etc/hostname", "r", encoding="utf-8") as f:
        container_id = f.read().strip()
        try:
            docker.network.connect(os.environ["NETWORK_NAME"], container_id)
        except DockerException as e:
            if re.search(r"already exists in network", e.stderr):
                log.debug("Container is already associated")
            else:
                raise e

    yield docker

    docker.network.disconnect(os.environ["NETWORK_NAME"], container_id)
    docker.compose.stop()
    # docker.compose.down()


def test_redirect_supported():
    """Ensures ECS API requests that aren't covered by local API are redirected to target AWS endpoint"""
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    response = ecs.list_clusters()

    assert "clusterArns" in response


def test_redirect_not_supported():
    """Ensures local API requests and any redirected requests that aren't supported return the expected failed response"""
    # TODO: Create request that will cause moto to return error response otherthan 500
    response = requests.post(
        os.environ.get("LOCAL_ECS_API_ENDPOINT"),
        headers={"x-amz-target": "non-existent-endpoint"},
        json={"foo": "doo"},
        timeout=5,
    )

    assert response.status_code == 422


def test_run_task(aws_credentials):
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    task = ecs.register_task_definition(**task_defs["fast_success"])
    response = ecs.run_task(
        taskDefinition=task["taskDefinition"]["taskDefinitionArn"],
    )
    log.debug("Run task response")
    log.debug(pformat(response))

    assert 1 == 2


@pytest.mark.skip()
def test_describe_tasks():
    pass


@pytest.mark.skip()
def test_list_tasks():
    pass
