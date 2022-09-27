from pydantic import BaseModel
from typing import List, Optional

from local_ecs_api.converters import DockerTask

import pickle
import boto3
import os
import re
from datetime import datetime
import logging

log = logging.getLogger(__file__)
log.setLevel(logging.DEBUG)


class CapacityProviderStrategy(BaseModel):
    base: int
    capacityProvider: str
    weight: int


class AwsvpcConfiguration(BaseModel):
    assignPublicIp: str
    securityGroups: List[str]
    subnets: List[str]


class NetworkConfiguration(BaseModel):
    awsvpcConfiguration: AwsvpcConfiguration


class ResourceRequirements(BaseModel):
    type: str
    value: str


class Environment(BaseModel):
    name: str
    value: str


class EnvironmentFiles(BaseModel):
    type: str
    value: str


class ContainerOverrides(BaseModel):
    command: List[str]
    cpu: int
    environment: List[Environment]
    environmentFiles: List[EnvironmentFiles]
    memory: int
    memoryReservation: int
    name: str
    resourceRequirements: List[ResourceRequirements]


class EphemeralStorage(BaseModel):
    sizeInGiB: int


class DeviceName(BaseModel):
    deviceName: str
    deviceType: str


class PlacementConstraints(BaseModel):
    expression: str
    type: str


class PlacementStrategy(BaseModel):
    field: str
    type: str


class Tags(BaseModel):
    key: str
    type: str


class InferenceAccelerators(BaseModel):
    deviceName: str
    deviceType: str


class Overrides(BaseModel):
    containerOverrides: Optional[List[ContainerOverrides]]
    cpu: str
    ephemeralStorage: EphemeralStorage
    executionRoleArn: str
    inferenceAcceleratorOverrides: List[InferenceAccelerators]
    memory: str
    taskRoleArn: str


class RunTaskRequest(BaseModel):
    capacityProviderStrategy: Optional[List[CapacityProviderStrategy]]
    cluster: Optional[str] = "default"
    count: Optional[int] = 1
    enableECSManagedTags: Optional[bool]
    enableExecuteCommand: Optional[bool]
    group: Optional[str]
    launchType: Optional[str]
    networkConfiguration: Optional[AwsvpcConfiguration]
    overrides: Optional[Overrides]
    placementConstraints: Optional[List[PlacementConstraints]]
    placementStrategy: Optional[List[PlacementStrategy]]
    platformVersion: Optional[str]
    propagateTags: Optional[str]
    propagateTags: Optional[str]
    referenceId: Optional[str]
    startedBy: Optional[str]
    tags: Optional[List[Tags]]
    taskDefinition: str


class Failures(BaseModel):
    arn: str
    detail: str
    reason: str


class Details(BaseModel):
    name: str
    value: str


class Attributes(BaseModel):
    name: str
    targetId: str
    targetType: str
    value: str


class Attachments(BaseModel):
    id: str
    status: str
    type: str
    defails: List[Details]


class ManagedAgents(BaseModel):
    lastStartedAt: int
    lastStatus: str
    name: str
    reason: str


class NetworkBindings(BaseModel):
    bindIP: str
    containerPort: int
    hostPort: int
    protocol: str


class NetworkInterfaces(BaseModel):
    attachmentId: str
    ipv6Address: str
    privateIpv4Address: str


class Containers(BaseModel):
    containerArn: str
    cpu: str
    exitCode: int
    gpuIds: List[str]
    healthStatus: str
    image: str
    imageDigest: str
    lastStatus: str
    managedAgents: List[ManagedAgents]
    memory: str
    memoryReservation: str
    name: str
    networkBindings: List[NetworkBindings]
    networkInterfaces: List[NetworkInterfaces]
    reason: str
    runtimeId: str
    taskArn: str


class Tasks(BaseModel):
    attachments: Optional[List[Attachments]]
    attributes: Optional[List[Attributes]]
    availabilityZone: Optional[str]
    capacityProviderName: Optional[str]
    clusterArn: Optional[str]
    connectivity: Optional[str]
    connectivityAt: Optional[int]
    containerInstanceArn: Optional[str]
    cpu: Optional[str]
    createdAt: Optional[int]
    desiredStatus: Optional[str]
    enableExecuteCommand: Optional[bool]
    executionStoppedAt: Optional[int]
    group: Optional[str]
    healthStatus: Optional[str]
    lastStatus: Optional[str]
    launchType: Optional[str]
    memory: Optional[str]
    platformFamily: Optional[str]
    platformVersion: Optional[str]
    pullStartedAt: Optional[int]
    pullStoppedAt: Optional[int]
    startedAt: Optional[int]
    startedBy: Optional[str]
    stopCode: Optional[str]
    stoppedAt: Optional[int]
    stoppedReason: Optional[str]
    stoppingAt: Optional[int]
    taskArn: Optional[str]
    taskDefinitionArn: Optional[str]
    version: Optional[int]
    containers: Optional[List[Containers]]
    ephemeralStorage: Optional[EphemeralStorage]
    inferenceAccelerators: Optional[List[InferenceAccelerators]]
    overrides: Optional[List[Overrides]]
    tags: Optional[List[Tags]]


class RunTaskResponse(BaseModel):
    failures: List[Failures] = List
    tasks: List[Tasks] = List


class DescribeTasksRequest(BaseModel):
    cluster: Optional[str]
    include: Optional[List[str]]
    tasks: List[str]


class DescribeTasksResponse(BaseModel):
    failures: List[Failures] = List
    tasks: List[Tasks] = List


class ListTasksRequest(BaseModel):
    cluster: Optional[str]
    containerInstance: Optional[str]
    desiredStatus: Optional[str]
    family: Optional[str]
    launchType: Optional[str]
    maxResults: Optional[int]
    nextToken: Optional[str]
    serviceName: Optional[str]
    startedBy: Optional[str]


class ListTasksResponse(BaseModel):
    nextToken: Optional[str]
    taskArns: List[str] = []


class RunTaskBackend:
    """
    Backend class used for converting local Docker container metadata into
    ECS compatible response attributes
    """

    def __init__(self, request: RunTaskRequest, docker_task: DockerTask):
        self.request = request
        self.docker_task = docker_task
        self.metadata = {}

        aws_attr = self._parse_arn(self.docker_task.task_def_arn)
        self.region = aws_attr["region"]
        self.account_id = aws_attr["account_id"]

        self.service_names = [
            c["name"] for c in self.docker_task.task_def["containerDefinitions"]
        ]

        self.essential_containers = [
            c["name"]
            for c in self.docker_task.task_def["containerDefinitions"]
            if c["essential"] is True
        ]
        self.task_arn = (
            f"arn:aws:ecs:{self.region}:{self.account_id}:task/{self.docker_task.id}"
        )

    def pull(self):
        self.containers = self.docker_task.docker.ps()

    def is_failure(self):
        for id in self.containers:
            if self.docker_task.docker.container.inspect(id).state.exit_code != 0:
                return True

        return False

    def get_status(self):
        full_cmd = self.docker_task.docker.docker_compose_cmd + [
            "ls",
            "--format",
            "json",
            "--all",
        ]
        for proj in json.loads(run(full_cmd)):
            if (
                proj["Name"]
                == self.docker_task.docker.compose.client_config.compose_project_name
            ):
                # remove status count (e.g. running(1) -> running)
                status = re.sub(r"\([0-9]+\)$", "", proj["Status"])
                if status == "running":
                    return "RUNNING"
                elif status == "exited":
                    return "STOPPED"
        # uncomment and replace above with once PR is merged: https://github.com/gabrieldemarmiesse/python-on-whales/pull/368
        # for proj in self.docker_task.docker.compose.ls():
        #     if proj.name == self.docker_task.compose_project_name:
        #         # remove status count (e.g. running(1) -> running)
        #         if proj.status == "running":
        #             return "RUNNING"
        #         elif proj.status == "exited":
        #             return "STOPPED"

    def get_task(self):
        started_at = min([datetime.timestamp(c.created) for c in self.containers])
        return {
            "lastStatus": self.get_status(),
            "createdAt": self.docker_task.created_at,
            "executionStoppedAt": self.get_execution_stopped_at(),
            "healthStatus": self.get_task_health_status(),
            # TODO get more precise times for below attributes
            "pullStartedAt": self.docker_task.created_at,
            "pullStoppedAt": self.docker_task.created_at,
            "startedAt": started_at,
            "taskArn": self.task_arn,
        }

    def get_execution_stopped_at(self):
        finished_ts = [datetime.timestamp(c.state.finished_at) for c in self.containers]

        # containers that are still running return a negative timestamp
        if min(finished_ts) < 0:
            return 0
        return max(finished_ts)

    def get_task_health_status(self):
        for c in self.containers:
            if c.name in self.essential_containers:
                status = getattr(c.state, "health", "UKNOWN")
                if status == "healthy":
                    continue
                else:
                    return status

    @staticmethod
    def _parse_arn(resource_arn):
        match = re.match(
            "^arn:aws:ecs:(?P<region>[^:]+):(?P<account_id>[^:]+):(?P<service>[^:]+)/(?P<id>.*)$",
            resource_arn,
        )
        return match.groupdict()

    def get_containers(self) -> List[Containers]:
        response = []

        for id in self.containers:
            c = self.docker_task.docker.container.inspect(id)
            response.append(
                Containers(
                    containerArn=f"arn:aws:ecs:{self.region}:{self.account_id}:container/{c.id}",
                    cpu=c.host_config.cpu_shares,
                    exitCode=c.state.exit_code,
                    gpuIds=[],
                    # TODO find healthstatus attr
                    healthStatus=c.state.status,
                    image=c.config.image,
                    imageDigest=c.image,
                    lastStatus=c.state.status,
                    managedAgents=[],
                    memory=c.host_config.memory,
                    memoryReservation=c.host_config.memory_reservation,
                    name=c.name,
                    # TODO replace empty list with docker mapping
                    networkBindings=[],
                    # TODO replace empty list with docker mapping
                    networkInterfaces=[],
                    reason=c.state.error,
                    runtimeId=c.id,
                    taskArn=self.task_arn,
                )
            )
        return response


class ECSBackend:
    def __init__(self, pickle_path):
        self.tasks = {}
        self.pickle_path = pickle_path

    def save(self):
        with open(self.pickle_path, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)

    def describe_tasks(self, tasks: List[str], include=[]):
        """
        Returns ECS DescribeTask response replaced with local docker compose container values

        Arguments:
            tasks: List of task IDs or ARNs
            #TODO implement include argument
            include: List of additional attributes to include (only supports `TAG`)
        """
        response = {"tasks": [], "failures": []}

        for t in tasks:
            match = re.match(
                "^arn:aws:ecs:(?P<region>[^:]+):(?P<account_id>[^:]+):(?P<service>[^:]+)/(?P<id>.*)$",
                t,
            )
            if match:
                t = match.groupdict()["id"]
            task = self.tasks[t]
            task.pull()
            if task.is_failure():
                response.failures.append(
                    Failures(
                        arn=task.arn,
                        detail=task.logs,
                        # TODO: use exception message instead
                        reason="placeholder-reason",
                    )
                )

            response["tasks"].append(
                Tasks(
                    containers=task.get_containers(),
                    **task.get_task(),
                    **task.request.dict(),
                )
            )

        return response

    def run_task(self, task_def_arn, overrides, count):
        ecs = boto3.client("ecs", endpoint_url=os.environ.get("ECS_ENDPOINT_URL"))

        task_def = ecs.describe_task_definition(taskDefinition=task_def_arn)
        task = DockerTask(task_def)

        task.create_docker_compose_stack(overrides)
        log.info("Running docker compose up")
        task.up(count)

        return task

    def list_tasks(
        self,
        cluster: Optional[str] = None,
        family: Optional[str] = None,
        launch_type: Optional[str] = None,
        service_name: Optional[str] = None,
        desired_status: Optional[str] = None,
        started_by: Optional[str] = None,
        container_instance: Optional[str] = None,
        max_results: Optional[int] = None,
    ):
        arns = []
        for id, task in self.tasks.items():
            if cluster is not None and task.cluster != cluster:
                continue
            elif family is not None and task.family != family:
                continue
            elif launch_type is not None and task.launch_type != launch_type:
                continue
            elif service_name is not None and service_name not in task.service_names:
                continue
            elif desired_status is not None and task.get_status() != desired_status:
                continue
            elif started_by is not None and task.startedby != started_by:
                continue
            elif (
                container_instance is not None
                and task.container_instance != container_instance
            ):
                continue

            arns.append(task.task_arn)

        return arns[:max_results]
