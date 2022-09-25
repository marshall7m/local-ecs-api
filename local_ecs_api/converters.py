from glob import glob
import os
import subprocess
import logging
import json
import yaml
from hashlib import sha1
import hmac
from tempfile import NamedTemporaryFile
import shlex
from pprint import pformat
from python_on_whales import DockerClient
import ipaddress
import random
import struct
from datetime import datetime
import uuid

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


class DockerTask:
    def __init__(self, task_def, docker=DockerClient()):
        self.docker = docker

        self.task_def = task_def["taskDefinition"]
        self.task_def_arn = self.task_def["taskDefinitionArn"]
        self.task_name = self.task_def_arn.split("task-definition/")[-1].replace(
            ":", "-"
        )
        self.compose_dir = os.path.join(COMPOSE_DEST, f".{self.task_name}-compose")
        self.hash_path = os.path.join(self.compose_dir, "compose-hash.json")

    def generate_local_task_compose_file(self, task_def, path):

        with NamedTemporaryFile(delete=False, mode="w+") as tmp:
            json.dump(task_def, tmp)
            tmp.flush()

            cmd = f"ecs-cli local create --force --task-def-file {tmp.name} --output {path}"
            log.debug(f"Running command: {cmd}")
            subprocess.run(shlex.split(cmd), check=True)

        return path

    def get_docker_compose_stack(self):

        if not os.path.exists(self.compose_dir):
            raise Exception("compose dir does not exists -- task not runned")

        log.debug("Docker compose directory: " + self.compose_dir)
        self.add_compose_files()

    def create_docker_compose_stack(self, overrides):
        log.info("Creating ECS local Docker network")
        try:
            self.docker.network.create(
                ECS_NETWORK_NAME,
                attachable=True,
                driver="bridge",
                gateway="169.254.170.1",
                subnet="169.254.170.0/24",
            )
        # TODO: create more granular docker catch
        except DockerException:
            log.info("Network already exists: " + ECS_NETWORK_NAME)

        task_def = self.task_def
        if overrides:
            log.info("Applying RunTask overrides to task definition")
            task_def = self.merge_overrides(self.task_def, overrides)
            log.debug(f"Merged Task Definition:\n{pformat(task_def)}")

        self.generate_compose_files(task_def)

        self.add_compose_files()

    def generate_compose_files(self, task_def):
        compose_hash = sha1(
            json.dumps(task_def, sort_keys=True, default=str).encode("cp037")
        ).hexdigest()

        if os.path.exists(self.hash_path):
            with open(self.hash_path, "r") as f:
                cache_hash = json.load(f)["hash"]

            if hmac.compare_digest(str(compose_hash), str(cache_hash)):
                log.debug("Using cache docker compose directory")
                return

        log.debug("Generating docker compose files")

        self.generate_local_task_compose_file(
            task_def,
            os.path.join(self.compose_dir, "docker-compose.ecs-local.tasks.yml"),
        )

        self.docker.client_config.compose_files.extend(
            glob(self.compose_dir + "/*[!override].yml")
            + glob(self.compose_dir + "/*override.yml")
        )
        self.generate_local_compose_network_file(
            os.path.join(
                self.compose_dir, "docker-compose.ecs-local.network-override.yml"
            )
        )

        log.debug("Creating/modifying compose hash file")
        with open(self.hash_path, "w") as f:
            json.dump({"hash": compose_hash}, f)

    def get_env_files():
        env_file_overrides = {}
        s3 = boto3.client(
            "s3", endpoint_url=os.environ.get("S3_ENDPOINT_URL")
        )
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

#  sets URI used to retrieve credentials for local container
#                         # uses user-defined URI for container
#                         if os.environ.get(
#                             "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", False
#                         ):
#                             override["environment"].append(
#                                 {
#                                     "name": "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
#                                     "value": os.environ[
#                                         "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"
#                                     ],
#                                 }
#                             )
#                         else:
#                             # uses task role ARN URI for container
#                             override["environment"].append(
#                                 {
#                                     "name": "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
#                                     "value": os.path.join(
#                                         "/role-arn",
#                                         hasattr(
#                                             override,
#                                             "taskRoleArn",
#                                             task_def["taskRoleArn"],
#                                         ),
#                                     ),
#                                 }
#                             )

    def merge_overrides(self, task_def: str, overrides):
        log.debug("Merging overrides")
        for k, v in overrides.items():
            if k != "containerOverrides":
                task_def[k] = v
            else:
                for container_override in v:
                    for idx, container in enumerate(task_def["containerDefinitions"]):
                        if container_override["name"] == container["name"]:
                            for attr, value in container_override.items():
                                if attr == "environment":
                                    task_def["containerDefinitions"][idx]["environment"] = [
                                        {"key": key, "value": value} for key, value in {
                                            **{env["key"]: env["value"] for env in container["environment"]},
                                            **{env["key"]: env["value"] for env in value}, 
                                        }.items()
                                    ]
                                elif attr == "environmentFiles":
                                    for path in value:
                                        if path not in task_def["containerDefinitions"][idx]["environmentFiles"]:
                                            task_def["containerDefinitions"][idx]["environmentFiles"].append(path)
                                elif attr == "resourceRequirements":
                                    task_def["containerDefinitions"][idx]["resourceRequirements"] = [
                                        {"type": key, "value": value} for key, value in {
                                        **{env["type"]: env["value"] for env in value}, 
                                        **{env["type"]: env["value"] for env in container["resourceRequirements"]}}
                                    ]
                                else:
                                    task_def["containerDefinitions"][idx][attr] = value

        return task_def

    def up(self, count: int):

        for i in range(count):
            log.debug(f"Count: {i+1}/{count}")
            self.docker.compose.up(build=True, detach=True, log_prefix=False)
        # TODO create more precise ts by using while proj state != "running"

        self.id = uuid.uuid4()
        self.created_at = datetime.timestamp(datetime.now())

    def add_compose_files(self):
        # order of list is important to ensure that the override compose files take precedence
        # over original compose files

        all_compose_files = (
            glob(self.compose_dir + "/*[!override].yml")
            + glob(self.compose_dir + "/*override.yml")
            + [
                os.path.join(
                    os.path.dirname(__file__), "docker-compose.local-endpoint.yml"
                )
            ]
            + glob(os.path.join(COMPOSE_DEST, f"*.{self.task_name}.yml"))
        )
        compose_files = set()
        for path in all_compose_files:
            if path not in self.docker.client_config.compose_files:
                compose_files.add(path)

        self.docker.client_config.compose_files.extend(list(compose_files))

    def get_network_assigned_ips(self, network_name):
        return [
            ipaddress.IPv4Network(attr["IPv4Address"])[0]
            for attr in self.docker.network.inspect(network_name).containers.values()
        ]

    def generate_local_compose_network_file(self, path):
        local_subnet = self.docker.network.inspect(ECS_NETWORK_NAME).ipam.config[0][
            "Subnet"
        ]
        log.debug(f"Network: {ECS_NETWORK_NAME}")
        log.debug(f"Subnet: {local_subnet}")

        config = self.docker.compose.config()
        assigned = self.get_network_assigned_ips(ECS_NETWORK_NAME)
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


"""

RunTaskBackend(DockerTask):
-> add DockerTask to self attr


DockerTask -> scoped to running task def locally
"""
