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
    def __init__(self, task_def):
        self.task_def = task_def["taskDefinition"]
        self.task_def_arn = self.task_def["taskDefinitionArn"]
        self.task_name = self.task_def_arn.split("task-definition/")[-1].replace(
            ":", "-"
        )
        self.docker = DockerClient(compose_project_name=self.task_name)
        self.compose_dir = os.path.join(COMPOSE_DEST, f".{self.task_name}-compose")
        self.hash_path = os.path.join(self.compose_dir, "compose-hash.json")

    def generate_local_task_compose_file(self, task_def, path):

        with NamedTemporaryFile(delete=False, mode="w+") as tmp:
            json.dump(task_def, tmp)
            tmp.flush()

            cmd = f"ecs-cli local create --force --task-def-file {tmp.name} --output {path} --use-role"
            log.debug(f"Running command: {cmd}")
            subprocess.run(shlex.split(cmd), check=True)

        return path

    def create_docker_compose_stack(self, overrides=None):
        compose_hash_input = [self.task_def]
        overrides_def = None
        if overrides:
            log.info("Creating overrides task definition")
            overrides["containerDefinitions"] = overrides.pop("containerOverrides")
            overrides_def = overrides
            compose_hash_input.append(overrides_def)

        compose_hash = sha1()
        for v in compose_hash_input:
            compose_hash.update(
                json.dumps(v, sort_keys=True, default=str).encode("cp037")
            )
        compose_hash = compose_hash.hexdigest()

        generate = False
        if os.path.exists(self.hash_path):
            with open(self.hash_path, "r") as f:
                cache_hash = json.load(f)["hash"]

            if hmac.compare_digest(str(compose_hash), str(cache_hash)):
                log.info("Using cache docker compose directory")
            else:
                generate = True
        else:
            log.debug("Cache compose hash file doesn't exist")
            generate = True

        if generate:
            log.info("Generating docker compose files")
            self.generate_compose_files(self.task_def, overrides_def)

            log.info("Creating/modifying compose hash file")
            with open(self.hash_path, "w") as f:
                log.debug(f"New hash: {compose_hash}")
                json.dump({"hash": compose_hash}, f)

        self.add_compose_files()

    def generate_compose_files(self, task_def, overrides_def):
        os.makedirs(self.compose_dir, exist_ok=True)
        self.generate_local_task_compose_file(
            task_def,
            os.path.join(self.compose_dir, "docker-compose.ecs-local.tasks.yml"),
        )

        if overrides_def:
            self.generate_local_task_compose_file(
                overrides_def,
                os.path.join(
                    self.compose_dir, "docker-compose.ecs-local.run-task-override.yml"
                ),
            )

        self.docker.client_config.compose_files.extend(
            glob(self.compose_dir + "/*[!override].yml")
            + glob(self.compose_dir + "/*override.yml")
        )

    def up(self, count: int):
        docker = DockerClient(
            compose_files=[
                os.path.join(
                    os.path.dirname(__file__), "docker-compose.local-endpoint.yml"
                )
            ]
        )
        docker.compose.up(detach=True)

        log.debug("Running ")
        for i in range(count):
            log.debug(f"Count: {i+1}/{count}")
            self.docker.compose.up(build=True, detach=True, log_prefix=False)
        # TODO create more precise ts by using while proj state != "running"

        self.id = str(uuid.uuid4())
        self.created_at = datetime.timestamp(datetime.now())

    def add_compose_files(self):
        # order of list is important to ensure that the override compose files take precedence
        # over original compose files

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
