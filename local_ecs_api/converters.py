from glob import glob
import os
import subprocess
import logging
import json
import yaml
from hashlib import sha1
import boto3
import inspect
from tempfile import NamedTemporaryFile
import shlex
from urllib.parse import urlparse
from pprint import pformat
from local_ecs_api.models import RunTaskRequest, overrides
from python_on_whales import DockerClient
from python_on_whales.exceptions import DockerException
import ipaddress, random, struct
from collections import defaultdict

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

COMPOSE_DEST = os.environ.get("COMPOSE_DEST", "/tmp")
ECS_NETWORK_NAME = os.environ.get("ECS_NETWORK_NAME", "ecs-local-network")


def random_ip(network):
    network = ipaddress.IPv4Network(network)
    (network_int,) = struct.unpack(
        "!I", network.network_address.packed
    )  # make network address into an integer
    rand_bits = (
        network.max_prefixlen - network.prefixlen
    )  # calculate the needed bits for the host part
    rand_host_int = random.randint(0, 2**rand_bits - 1)  # generate random host part
    ip_address = ipaddress.IPv4Address(network_int + rand_host_int)  # combine the parts
    return ip_address.exploded


def generate_local_task_compose_file(task_def, path):

    with NamedTemporaryFile(delete=False, mode="w+") as tmp:
        json.dump(task_def, tmp)
        tmp.flush()

        cmd = f"ecs-cli local create --force --task-def-file {tmp.name} --output {path}"
        log.debug(f"Running command: {cmd}")
        subprocess.run(shlex.split(cmd), check=True)

    return path


def merge_overrides(task_def: str, overrides: overrides):
    log.debug("Merging container overrides")
    for override in overrides["containerOverrides"]:
        for idx, container in enumerate(task_def["containerDefinitions"]):
            if override["name"] == container["name"]:
                env_file_overrides = {}
                s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT_URL"))
                for env in overrides.get("environmentFiles", []):
                    log.debug("Merging env file overrides with env overrides")
                    if env["type"] == "s3":
                        parsed = urlparse(env["value"])
                        env_file = s3.get_object(
                            Bucket=parsed.netloc,
                            Key=parsed.path,
                        )["Body"].read()
                        iter_env = iter(env_file.split("="))
                        for v in iter_env:
                            env_file_overrides[v] = next(iter_env)
                    else:
                        # TODO: get actual botocore exception (ECS.Client.exceptions.ClientException?)
                        raise Exception("Env file type not supported")

                    # environment overrides take precedence over env file overrides
                    override["environment"] = [
                        {"name": k, "value": v}
                        for k, v in {
                            **env_file_overrides,
                            **{
                                env["key"]: env["value"]
                                for env in override["environment"]
                            },
                        }
                    ]

                    # sets URI used to retrieve credentials for local container
                    # uses user-defined URI for container
                    if os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", False):
                        override["environment"].append(
                            {
                                "name": "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
                                "value": os.environ[
                                    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"
                                ],
                            }
                        )
                    else:
                        # uses task role ARN URI for container
                        override["environment"].append(
                            {
                                "name": "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
                                "value": os.path.join(
                                    "/role-arn",
                                    hasattr(
                                        override, "taskRoleArn", task_def["taskRoleArn"]
                                    ),
                                ),
                            }
                        )

                task_def["containerDefinitions"][idx] = {**container, **override}
                break

    log.debug("Merging task overrides")
    for k, v in overrides.items():
        if k != "containerDefinitions":
            task_def[k] == v

    return task_def


def get_compose_dir(task_def, task_name):
    compose_dir_hash = sha1(
        json.dumps(task_def, sort_keys=True, default=str).encode("cp037")
    ).hexdigest()
    return os.path.join(COMPOSE_DEST, f".{task_name}-compose", compose_dir_hash)


def add_compose_files(docker, compose_dir, task_def, task_name):
    if os.path.exists(compose_dir):
        log.debug("Using cache docker compose directory")
    else:
        log.debug("Creating docker compose directory")
        os.makedirs(compose_dir)

        log.debug("Generating docker compose files")
        task_compose_file = os.path.join(
            compose_dir, "docker-compose.ecs-local.tasks.yml"
        )
        generate_local_task_compose_file(task_def, task_compose_file)
        docker.client_config.compose_files.extend(
            glob(compose_dir + "/*[!override].yml")
            + glob(compose_dir + "/*override.yml")
        )
        generate_local_compose_network_file(
            docker,
            os.path.join(compose_dir, "docker-compose.ecs-local.network-override.yml"),
        )

    # order of list is important to ensure that the override compose files take precedence
    # over original compose files
    all_compose_files = (
        glob(compose_dir + "/*[!override].yml")
        + glob(compose_dir + "/*override.yml")
        + [os.path.join(os.path.dirname(__file__), "docker-compose.local-endpoint.yml")]
        + glob(os.path.join(COMPOSE_DEST, f"*.{task_name}.yml"))
    )
    compose_files = set()
    for path in all_compose_files:
        if path not in docker.client_config.compose_files:
            compose_files.add(path)

    docker.client_config.compose_files.extend(list(compose_files))

    return docker


def get_docker_compose_stack(request: RunTaskRequest):
    docker = DockerClient()

    log.info("Creating ECS local Docker network")
    try:
        docker.network.create(
            ECS_NETWORK_NAME,
            attachable=True,
            driver="bridge",
            gateway="169.254.170.1",
            subnet="169.254.170.0/24",
        )
    # TODO: create more granular docker catch
    except DockerException:
        log.info("Network already exists: " + ECS_NETWORK_NAME)

    ecs = boto3.client("ecs", endpoint_url=os.environ.get("ECS_ENDPOINT_URL"))
    task_def = ecs.describe_task_definition(taskDefinition=request.taskDefinition)[
        "taskDefinition"
    ]
    task_name = request.taskDefinition.split("task-definition/")[-1].replace(":", "-")

    if request.overrides:
        log.info("Applying RunTask overrides to task definition")
        task_def = merge_overrides(task_def, request.overrides)
    log.debug(f"Merged Task Definition:\n{pformat(task_def)}")

    compose_dir = get_compose_dir(task_def, task_name)
    log.debug("Docker compose directory: " + compose_dir)

    docker = add_compose_files(docker, compose_dir, task_def, task_name)

    return docker


def generate_local_compose_network_file(docker, path):
    local_subnet = docker.network.inspect(ECS_NETWORK_NAME).ipam.config[0]["Subnet"]
    log.debug(f"Network: {ECS_NETWORK_NAME}")
    log.debug(f"Subnet: {local_subnet}")

    config = docker.compose.config()
    assigned = []
    for _ in range(len(config.services)):
        rand_ip = None
        while rand_ip is None or rand_ip in assigned:
            rand_ip = random_ip(local_subnet)
        assigned.append(rand_ip)

    file_content = {
        "version": "3.4",
        "networks": {ECS_NETWORK_NAME: {"external": True}},
        "services": {
            service: {"networks": {ECS_NETWORK_NAME: {"ipv4_address": assigned[i]}}}
            for i, service in enumerate(config.services)
        },
    }

    log.debug(f"Writing to path:\n{pformat(file_content)}")
    with open(path, "w+") as f:
        yaml.dump(file_content, f)


def get_compose_failures(docker):

    ps = docker.compose.ps()

    log.debug("docker ps: " + str(ps))
