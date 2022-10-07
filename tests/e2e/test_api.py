import os
import logging
import re
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
def local_api():
    os.environ["NETWORK_NAME"] = "local-ecs-api-tests"
    os.environ["LOCAL_ECS_API_ENDPOINT"] = "http://" + "local-ecs-api" + ":8000"
    docker = DockerClient(compose_files=[os.path.join(FILE_DIR, "docker-compose.yml")])

    docker.compose.up(build=True, detach=True, quiet=True)

    yield docker

    docker.compose.stop()
    docker.compose.down()


@pytest.fixture(scope="module", autouse=True)
def connect_tests_to_api(local_api):
    # CI env var will be set if running in GitHub Action job
    if not os.environ.get("CI"):
        # needed only if running tests within container
        log.debug("Connecting dev container to API network")
        with open("/etc/hostname", "r", encoding="utf-8") as f:
            container_id = f.read().strip()
            try:
                docker = DockerClient()
                docker.network.connect(os.environ["NETWORK_NAME"], container_id)
            except DockerException as e:
                if re.search(r"already exists in network", e.stderr):
                    log.debug("Container is already associated")
                else:
                    raise e

        yield

        docker.network.disconnect(os.environ["NETWORK_NAME"], container_id)
    else:
        yield


def test_redirect_supported(aws_credentials):
    """Ensures ECS API requests that aren't covered by local API are redirected to target AWS endpoint"""
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    response = ecs.list_clusters()

    assert "clusterArns" in response


def test_run_task(aws_credentials):
    ecs = boto3.client("ecs", endpoint_url=os.environ.get("LOCAL_ECS_API_ENDPOINT"))
    task = ecs.register_task_definition(**task_defs["fast_success"])
    response = ecs.run_task(
        taskDefinition=task["taskDefinition"]["taskDefinitionArn"],
    )
    log.debug("Run task response")
    log.debug(pformat(response))


@pytest.mark.skip()
def test_describe_tasks():
    pass


@pytest.mark.skip()
def test_list_tasks():
    pass
