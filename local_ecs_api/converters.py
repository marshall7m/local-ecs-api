import ipaddress
import json
import logging
import os
import random
import re
import shlex
import struct
import subprocess
import uuid
from glob import glob
from pprint import pformat
from tempfile import NamedTemporaryFile

import boto3
import yaml
from python_on_whales import DockerClient
from python_on_whales.exceptions import DockerException

log = logging.getLogger("local-ecs-api")
log.setLevel(logging.DEBUG)

# name of the docker network that will host the ecs endpoint and ecs task containers
ECS_NETWORK_NAME = "ecs-local-network"
# directory where the generated docker compose file will be stored
COMPOSE_DEST = os.environ.get("COMPOSE_DEST", "/tmp")
# pre-existing docker networks to connect the ecs endpoint and ecs task containers to
EXTERNAL_NETWORKS = [
    net for net in os.environ.get("ECS_EXTERNAL_NETWORKS", "").split(",") if net != ""
]
DOCKER_PROJECT_PREFIX = "local-ecs-task-"


def random_ip(network: str) -> str:
    """
    Returns a random IPv4 IP address within the scope of the input CIDR range

    Arguments:
        network: CIDR range
    """
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
    """Handles creating and running local docker compose projects from ECS task definition"""

    def __init__(self, task_def: dict):
        self.task_def: str = task_def["taskDefinition"]
        self.task_def_arn: str = self.task_def["taskDefinitionArn"]
        self.task_name: str = (
            self.task_def_arn.split("task-definition/")[-1]
            .replace("-", "_")
            .replace(":", "-v")
        )
        self.id: str = str(uuid.uuid4())
        self.compose_dir: str = os.path.join(
            COMPOSE_DEST, f".{self.task_name}-{self.id[:4]}"
        )

        self.compose_task_filepath = os.path.join(
            self.compose_dir, "docker-compose.ecs-local.task.yml"
        )
        self.compose_run_task_overrides_filepath = os.path.join(
            self.compose_dir, "docker-compose.ecs-local.run-task-override.yml"
        )
        self.compose_network_filepath = os.path.join(
            self.compose_dir, "docker-compose.ecs-local.task-network-override.yml"
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

    def generate_local_task_compose_file(self, task_def: dict, path: str) -> str:
        """
        Creates docker compose file based on input ECS task definition

        Arguments:
            task_def: ECS task definition
            path: Absolute path to output the docker compose file to
        """
        with NamedTemporaryFile(delete=False, mode="w+") as tmp:
            json.dump(task_def, tmp)
            tmp.flush()

            cmd = f"ecs-cli local create --force --task-def-file {tmp.name} --output {path} --use-role"
            log.debug("Running command: %s", cmd)
            subprocess.run(shlex.split(cmd), check=True)

        return path

    def create_docker_compose_stack(self, overrides=None) -> None:
        """Generates docker compose files and adds the files to the docker compose client"""
        os.makedirs(self.compose_dir, exist_ok=True)

        self.generate_local_task_compose_file(self.task_def, self.compose_task_filepath)
        # need to add generated compose file before running generate_local_compose_network_file
        # for parsing compose task services
        self.docker.client_config.compose_files.append(self.compose_task_filepath)

        task_role_arn = self.task_def.get("taskRoleArn")

        if overrides:
            log.info("Creating overrides task definition")
            overrides["containerDefinitions"] = overrides.pop("containerOverrides")

            self.generate_local_task_compose_file(
                overrides, self.compose_run_task_overrides_filepath
            )
            self.docker.client_config.compose_files.append(
                self.compose_run_task_overrides_filepath
            )

            task_role_arn = overrides.get("taskRoleArn", task_role_arn)

        self.generate_local_compose_network_file(
            self.compose_network_filepath, task_role_arn
        )
        self.docker.client_config.compose_files.append(self.compose_network_filepath)
        # order of list is important to ensure that the override compose files take precedence
        # over original compose files and user-defined compose files take precendence over
        # override files
        all_compose_files = glob(self.compose_dir + "/*.override.yml") + glob(
            os.path.join(COMPOSE_DEST, f"*.{self.task_name}.yml")
        )
        compose_files = set()
        for path in all_compose_files:
            if path not in self.docker.client_config.compose_files:
                compose_files.add(path)

        self.docker.client_config.compose_files.extend(list(compose_files))

    def setup_task_secrets(self) -> None:
        """
        Sets environment variables for the task's AWS Secret Manager and System Manager Parameter Store values.
        The AWS credentials needed to retrieve the values must be set beforehand.
        """
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

    def assume_task_execution_role(self, execution_role: str) -> None:
        """
        Assumes the ECS task definition's associated task execution role

        Arguments:
            execution_role: ECS task execution role ARN
        """
        log.debug(f"Using task execution role: {execution_role}")
        sts = boto3.client("sts", endpoint_url=os.environ.get("STS_ENDPOINT"))

        creds = sts.assume_role(
            RoleArn=execution_role, RoleSessionName=f"LocalTask-{self.id}"
        )["Credentials"]

        os.environ["AWS_ACCESS_KEY_ID"] = creds["AccessKeyId"]
        os.environ["AWS_SECRET_ACCESS_KEY"] = creds["SecretAccessKey"]
        os.environ["AWS_SESSION_TOKEN"] = creds["SessionToken"]

    def ecs_endpoint_up(self) -> None:
        """Setup and run docker compose up for ECS endpoint"""
        if all(
            [
                os.environ.get("ECS_ENDPOINT_AWS_PROFILE"),
                os.environ.get("ECS_AWS_CREDS_VOLUME_NAME"),
            ]
        ):
            log.debug(
                "Using AWS credentials volume mount override file for ECS endpoint"
            )
            creds_overwrite_path = os.path.join(
                os.path.dirname(__file__), "docker-compose.local-endpoint.aws_creds.yml"
            )

            if creds_overwrite_path not in self.docker.client_config.compose_files:
                # adds volume as an external volume in endpoint compose project
                self.docker_ecs_endpoint.client_config.compose_files.append(
                    creds_overwrite_path
                )

        self.docker_ecs_endpoint.compose.up(quiet=True, detach=True)

        log.debug("Adding custom external docker networks to ECS endpoint container")
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

    def up(self, count: int, overrides=None) -> None:
        """
        Runs ECS endpoint if not exists and run ECS task locally

        Arguments:
            count: (Not supported) Number of docker compose projects that should be created for task
            overrides: List of container overrides
        """
        log.info("Running ECS endpoint service")
        self.ecs_endpoint_up()

        log.info("Generating docker compose files")
        self.create_docker_compose_stack(overrides)
        log.debug("Compose files:")
        log.debug(pformat(self.docker.client_config.compose_files))

        # preserve env vars before creating docker compose related env vars
        _environ = os.environ.copy()

        execution_role = self.task_def.get("executionRoleArn")
        if overrides:
            execution_role = overrides.get("executionRoleArn", execution_role)

        try:
            if execution_role:
                log.info("Assuming task execution role")
                self.assume_task_execution_role(execution_role)

            log.info("Setting env vars for task secrets")
            self.setup_task_secrets()

            for i in range(count):
                log.debug("Count: %i/%i", i + 1, count)
                self.docker.compose.up(
                    quiet=True, build=True, detach=True, log_prefix=False
                )

        finally:
            # removes secrets used in docker compose up environment
            os.environ.clear()
            os.environ.update(_environ)

    def generate_local_compose_network_file(self, path: str, task_role_arn) -> dict:
        """
        Creates docker compose file for assigning an IP addresses to the task
        container. This is needed to ensure task container IP's don't conflict
        with ECS endpoint within docker network.

        Arguments:
            path: Absolute path to output the docker compose file to
            task_role_arn: ECS task role ARN
        """
        docker_inspect = self.docker.network.inspect(ECS_NETWORK_NAME)
        network_subnet_cidr = docker_inspect.ipam.config[0]["Subnet"]

        # get list of IPs already assigned within docker network
        # network subnet/gateway IPs
        # NOTE: can't rely on docker network inspect results to get Gateway IP given
        # it's not always an attribute in ipam config (only Subnet)
        subnet_ip = network_subnet_cidr.split("/")[0]
        assigned = [subnet_ip, subnet_ip[:-2] + ".1"]
        assigned.extend(
            [attr.ipv4_address for attr in docker_inspect.containers.values()]
        )

        # compose service network attribute
        service_networks = {}
        # compose service network attribute for custom external networks
        external_service_networks = {}

        # registers all networks as external and independent from docker compose project
        networks = {ECS_NETWORK_NAME: {"external": True}}

        for network in EXTERNAL_NETWORKS:
            networks[network] = {"external": True}
            external_service_networks[network] = {}

        # parses docker compose file for task into Config object
        config = self.docker.compose.config()
        for service in config.services:
            rand_ip = None
            # gets random IP that isn't assigned within docker network
            while rand_ip is None or rand_ip in assigned:
                rand_ip = random_ip(network_subnet_cidr)
            assigned.append(rand_ip)

            service_networks[service] = {
                "environment": [
                    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI=/role/"
                    + task_role_arn.rsplit("/", maxsplit=1)[-1]
                ],
                "networks": {
                    **{ECS_NETWORK_NAME: {"ipv4_address": rand_ip}},
                    **external_service_networks,
                },
            }

        file_content = {
            "version": "3.4",
            "networks": networks,
            "services": service_networks,
        }

        log.debug("Writing to path:\n%s", pformat(file_content))
        with open(path, "w+") as f:
            yaml.dump(file_content, f)

        return file_content
