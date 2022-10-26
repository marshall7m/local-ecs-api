from glob import glob
import os
import uuid
import subprocess
import logging
import json
from tempfile import NamedTemporaryFile
import shlex
from pprint import pformat
import re

import ipaddress
import boto3
import random
import yaml
import struct
from python_on_whales import DockerClient
from python_on_whales.exceptions import DockerException

log = logging.getLogger("local-ecs-api")
log.setLevel(logging.DEBUG)

ECS_NETWORK_NAME = "ecs-local-network"
COMPOSE_DEST = os.environ.get("COMPOSE_DEST", "/tmp")
EXTERNAL_NETWORKS = [
    net for net in os.environ.get("ECS_EXTERNAL_NETWORKS", "").split(",") if net != ""
]
DOCKER_PROJECT_PREFIX = "local-ecs-task-"


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


class DockerTask:
    def __init__(self, task_def):
        self.task_def = task_def["taskDefinition"]
        self.task_def_arn = self.task_def["taskDefinitionArn"]
        self.task_name = (
            self.task_def_arn.split("task-definition/")[-1]
            .replace("-", "_")
            .replace(":", "-v")
        )
        self.id = str(uuid.uuid4())
        self.compose_dir = os.path.join(
            COMPOSE_DEST, f".{self.task_name}-{self.id[:4]}"
        )

        self.docker = DockerClient(
            compose_project_name=DOCKER_PROJECT_PREFIX + self.id,
            compose_project_directory=self.compose_dir,
        )

        self.docker.client_config.compose_files = []
        self.docker_ecs_endpoint = DockerClient(
            compose_files=[
                os.path.join(
                    os.path.dirname(__file__), "docker-compose.local-endpoint.yml"
                )
            ]
        )

    def generate_local_task_compose_file(self, task_def, path):

        with NamedTemporaryFile(delete=False, mode="w+") as tmp:
            json.dump(task_def, tmp)
            tmp.flush()

            cmd = f"ecs-cli local create --force --task-def-file {tmp.name} --output {path} --use-role"
            log.debug("Running command: %s", cmd)
            subprocess.run(shlex.split(cmd), check=True)

        return path

    def create_docker_compose_stack(self, overrides=None):
        log.info("Generating docker compose files")
        os.makedirs(self.compose_dir, exist_ok=True)

        task_path = self.generate_local_task_compose_file(
            self.task_def,
            os.path.join(self.compose_dir, "docker-compose.ecs-local.task.yml"),
        )
        self.docker.client_config.compose_files.append(task_path)

        self.generate_local_compose_network_file(
            os.path.join(
                self.compose_dir, "docker-compose.ecs-local.task-network-override.yml"
            )
        )

        if overrides:
            log.info("Creating overrides task definition")
            overrides["containerDefinitions"] = overrides.pop("containerOverrides")

            self.generate_local_task_compose_file(
                overrides,
                os.path.join(
                    self.compose_dir, "docker-compose.ecs-local.run-task-override.yml"
                ),
            )

        # order of list is important to ensure that the override compose files take precedence
        # over original compose files and user-defined compose files take precendence over
        # override files

        all_compose_files = (
            glob(self.compose_dir + "/*[!override].yml")
            + glob(self.compose_dir + "/*override.yml")
            + glob(os.path.join(COMPOSE_DEST, f"*.{self.task_name}.yml"))
        )
        compose_files = set()
        for path in all_compose_files:
            if path not in self.docker.client_config.compose_files:
                compose_files.add(path)

        self.docker.client_config.compose_files.extend(list(compose_files))

    def setup_task_secrets(self):
        ssm = boto3.client("ssm", endpoint_url=os.environ.get("SSM_ENDPOINT_URL"))
        sm = boto3.client(
            "secretsmanager", endpoint_url=os.environ.get("SECRET_MANAGER_ENDPOINT_URL")
        )

        for container in self.task_def["containerDefinitions"]:
            for secret in container.get("secrets", []):
                # scopes env vars to container by using container name as prefix.
                # when ecs-cli converts task def to compose, it will convert
                # all secrets to use this format within compose environment section
                name = f"{container['name']}_{secret['name']}"
                secret_type = secret["valueFrom"].split(":")[2]

                if secret_type == "ssm":
                    os.environ[name] = ssm.get_parameter(
                        Name=secret["valueFrom"]
                        .split(":")[-1]
                        .removeprefix("parameter/"),
                        WithDecryption=True,
                    )["Parameter"]["Value"]
                elif secret_type == "secretsmanager":
                    os.environ[name] = sm.get_secret_value(
                        SecretId=secret["valueFrom"]
                    )["SecretString"]
                else:
                    raise Exception(f"Secret type is not valid: {secret_type}")

    def assume_task_execution_role(self, execution_role):
        log.debug(f"Using task execution role: {execution_role}")
        sts = boto3.client("sts", endpoint_url=os.environ.get("STS_ENDPOINT"))

        creds = sts.assume_role(
            RoleArn=execution_role, RoleSessionName=f"LocalTask-{self.id}"
        )["Credentials"]

        os.environ["AWS_ACCESS_KEY_ID"] = creds["AccessKeyId"]
        os.environ["AWS_SECRET_ACCESS_KEY"] = creds["AccessKeyId"]
        os.environ["AWS_SESSION_TOKEN"] = creds["AccessKeyId"]

    def ecs_endpoint_up(self):
        if all(
            [
                os.environ.get("ECS_ENDPOINT_AWS_PROFILE"),
                os.environ.get("ECS_AWS_CREDS_VOLUME_NAME"),
            ]
        ):
            # self.setup_aws_creds_volume()

            creds_overwrite_path = os.path.join(
                os.path.dirname(__file__), "docker-compose.local-endpoint.aws_creds.yml"
            )

            if creds_overwrite_path not in self.docker.client_config.compose_files:
                # adds volume as an external volume in endpoint compose project
                self.docker_ecs_endpoint.client_config.compose_files.append(
                    creds_overwrite_path
                )

        self.docker_ecs_endpoint.compose.up(quiet=True, detach=True)
        for network in EXTERNAL_NETWORKS:
            endpoint_container_name = (
                self.docker_ecs_endpoint.compose.config()
                .services["ecs-local-endpoints"]
                .container_name
            )
            try:
                self.docker_ecs_endpoint.network.connect(
                    network, endpoint_container_name
                )
            except DockerException as err:
                if re.search(r"already exists in network", err.stderr):
                    log.debug("Container is already associated")
                else:
                    raise err

    def up(self, count: int, overrides=None):
        log.info("Running ECS endpoint service")
        self.ecs_endpoint_up()

        self.create_docker_compose_stack(overrides)
        log.debug("Compose files:")
        log.debug(pformat(self.docker.client_config.compose_files))

        _environ = os.environ.copy()

        if overrides:
            execution_role = overrides.get("executionRoleArn") or self.task_def.get(
                "executionRoleArn"
            )
        else:
            execution_role = self.task_def.get("executionRoleArn")

        try:
            log.info("Assuming task execution role")
            if execution_role:
                self.assume_task_execution_role(execution_role)

            log.info("Setting env vars for task secrets")
            self.setup_task_secrets()

            for i in range(count):
                log.debug(f"Count: {i+1}/{count}")
                self.docker.compose.up(
                    quiet=True, build=True, detach=True, log_prefix=False
                )

        finally:
            # removes secrets used in docker compose up environment
            os.environ.clear()
            os.environ.update(_environ)

    def get_network_assigned_ips(self, network_name):
        return [
            attr.ipv4_address
            for attr in self.docker.network.inspect(network_name).containers.values()
        ]

    def generate_local_compose_network_file(self, path):
        local_subnet = self.docker.network.inspect(ECS_NETWORK_NAME).ipam.config[0][
            "Subnet"
        ]

        config = self.docker.compose.config()
        assigned = self.get_network_assigned_ips(ECS_NETWORK_NAME)

        service_networks = {}
        external_service_networks = {}
        networks = {ECS_NETWORK_NAME: {"external": True}}

        for network in EXTERNAL_NETWORKS:
            networks[network] = {"external": True}
            external_service_networks[network] = {}

        for service in config.services:
            rand_ip = None
            while rand_ip is None or rand_ip in assigned:
                rand_ip = random_ip(local_subnet)
            assigned.append(rand_ip)

            service_networks[service] = {
                "networks": {
                    **{ECS_NETWORK_NAME: {"ipv4_address": rand_ip}},
                    **external_service_networks,
                }
            }

        file_content = {
            "version": "3.4",
            "networks": networks,
            "services": service_networks,
        }

        log.debug(f"Writing to path:\n{pformat(file_content)}")
        with open(path, "w+") as f:
            yaml.dump(file_content, f)
