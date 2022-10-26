import os
import re
import json
import uuid
from datetime import datetime
import logging
from typing import List, Optional, Any, Dict
import pickle
from functools import cached_property

from pydantic import BaseModel
from python_on_whales.utils import run
from python_on_whales.exceptions import DockerException
import boto3

from local_ecs_api.converters import DockerTask

log = logging.getLogger("local-ecs-api")
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
    command: Optional[List[str]]
    cpu: Optional[int]
    environment: Optional[List[Environment]]
    environmentFiles: Optional[List[EnvironmentFiles]]
    memory: Optional[int]
    memoryReservation: Optional[int]
    name: str
    resourceRequirements: Optional[List[ResourceRequirements]]


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
    cpu: Optional[str]
    ephemeralStorage: Optional[EphemeralStorage]
    executionRoleArn: Optional[str]
    inferenceAcceleratorOverrides: Optional[List[InferenceAccelerators]]
    memory: Optional[str]
    taskRoleArn: Optional[str]


class RunTaskRequest(BaseModel):
    capacityProviderStrategy: Optional[List[CapacityProviderStrategy]]
    cluster: Optional[str] = "default"
    count: Optional[int] = 1
    enableECSManagedTags: Optional[bool]
    enableExecuteCommand: Optional[bool] = False
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
    tags: Optional[List[Tags]] = []
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
    stopCode: Optional[int]
    stoppedAt: Optional[int]
    stoppedReason: Optional[str]
    stoppingAt: Optional[int]
    taskArn: Optional[str]
    taskDefinitionArn: Optional[str]
    version: Optional[int]
    containers: Optional[List[Containers]]
    ephemeralStorage: Optional[EphemeralStorage]
    inferenceAccelerators: Optional[List[InferenceAccelerators]]
    overrides: Optional[Overrides]
    tags: Optional[List[Tags]]


class RunTaskResponse(BaseModel):
    failures: List[Failures] = []
    tasks: List[Tasks] = []


class DescribeTasksRequest(BaseModel):
    cluster: Optional[str]
    include: Optional[List[str]]
    tasks: List[str]


class DescribeTasksResponse(BaseModel):
    failures: List[Failures] = []
    tasks: List[Tasks] = []


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


class RunTaskBackend(DockerTask):
    """
    Backend class used for converting local Docker container metadata into
    ECS compatible response attributes
    """

    def __init__(self, task_def: str, **kwargs):
        DockerTask.__init__(self, task_def)
        self.request = kwargs
        self.metadata = {}
        if self.request.get("propagateTags") == "TASK_DEFINITION":
            # TODO: raise approriate botocore exception for when propagateTags == "SERVICE"
            self.request["tags"] += self.task_def["tags"]

        aws_attr = self._parse_arn(self.task_def_arn)
        self.region = aws_attr["region"]
        self.account_id = aws_attr["account_id"]
        self.cluster_arn = f"arn:aws:ecs:{self.region}:{self.account_id}:cluster/{self.request['cluster']}"

        self.essential_containers = [
            c["name"]
            for c in self.task_def["containerDefinitions"]
            if c["essential"] is True
        ]
        self.task_arn = f"arn:aws:ecs:{self.region}:{self.account_id}:task/{self.id}"

        self.started_at = datetime.timestamp(datetime.now())
        self.created_at = None
        self.stopping_at = None
        self.stopped_at = None
        self.stopping_at = None
        self._execution_stopped_at = None
        self._last_status = None

        self.run_exception = None

    @cached_property
    def platform_family(self):
        # use ecs endpoint to determine platformFamily in case
        # main docker project were to fail
        return self.docker_ecs_endpoint.compose.ps()[0].platform.upper()

    @cached_property
    def attachments(self) -> List[Attachments]:
        """
        Returns list of docker compose project attributes translated to the ECS
        response attachment attribute
        """
        attachments = []
        for c_id in self.docker.compose.ps():
            inspect = self.docker.container.inspect(c_id)
            for name, network in inspect.network_settings.networks.items():
                attachments.append(
                    Attachments(
                        id=str(uuid.uuid4()),
                        type="ElasticNetworkInterface",
                        status="ATTACHED",
                        defails=[
                            Details(name="privateDnsName", value=name),
                            Details(
                                name="networkInterfaceId", value=network.network_id
                            ),
                            Details(name="macAddress", value=network.mac_address),
                            Details(name="privateIPv4Address", value=network.gateway),
                        ],
                    )
                )
        return attachments

    @property
    def service_names(self):
        return [c.name for c in self.docker.compose.ps()]

    @property
    def last_status(self) -> str:
        """Returns Docker compose project status translated to lastStatus response attribute"""

        if self._last_status:
            return self._last_status

        full_cmd = self.docker.docker_compose_cmd + [
            "ls",
            "--format",
            "json",
            "--all",
        ]
        for proj in json.loads(run(full_cmd)):
            if proj["Name"] == self.docker.compose.client_config.compose_project_name:
                # remove status count (e.g. running(1) -> running)
                status = re.sub(r"\([0-9]+\)$", "", proj["Status"])
                if status == "running":
                    return "RUNNING"
                elif status == "exited":
                    return "STOPPED"
        # uncomment and replace above with once PR is merged: https://github.com/gabrieldemarmiesse/python-on-whales/pull/368
        # for proj in self.docker.compose.ls():
        #     if proj.name == self.compose_project_name:
        #         # remove status count (e.g. running(1) -> running)
        #         if proj.status == "running":
        #             return "RUNNING"
        #         elif proj.status == "exited":
        #             return "STOPPED"

    @last_status.setter
    def last_status(self, value):
        self._last_status = value

    @property
    def task_health_status(self) -> str:
        """
        Returns the health status of first container that reports a status other
        than `healthy` or returns a health status of `healthy` if all containers
        have a health status of healthy
        """
        for c in self.docker.compose.ps():
            if c.name in self.essential_containers:
                status = getattr(c.state, "health", "UKNOWN")
                if status == "healthy":
                    continue

                return status

        return "UNKNOWN"

    @property
    def execution_stopped_at(self) -> int:
        """
        Returns the timestamp of when all containers within the compose project have finished
        or returns `0` if any containers are still running
        """
        if self._execution_stopped_at:
            return self._execution_stopped_at

        finished_ts = [
            datetime.timestamp(c.state.finished_at) for c in self.docker.compose.ps()
        ]

        # containers that are still running return a negative timestamp
        if min(finished_ts) < 0:
            return

        return max(finished_ts)

    @execution_stopped_at.setter
    def execution_stopped_at(self, value):
        self._execution_stopped_at = value

    @staticmethod
    def _parse_arn(resource_arn: str) -> Dict[str, Any]:
        """Parses ECS-related ARN into dictionary"""
        match = re.match(
            "^arn:aws:ecs:(?P<region>[^:]+):(?P<account_id>[^:]+):(?P<service>[^:]+)/(?P<id>.*)$",
            resource_arn,
        )
        return match.groupdict()

    @property
    def containers(self) -> List[Containers]:
        """
        Returns docker compose projects attributes translated into the response Container model
        """
        response = []

        for c_id in self.docker.compose.ps():
            c = self.docker.container.inspect(c_id)
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

    @cached_property
    def cpu(self):
        return self.request.get("overrides", {}).get("cpu", self.task_def.get("cpu"))

    @cached_property
    def memory(self):
        return self.request.get("overrides", {}).get(
            "memory", self.task_def.get("memory")
        )

    def is_failure(self) -> bool:
        """Returns True if task contains any containers that have failed and True otherwise"""
        for c_id in self.docker.compose.ps():
            if self.docker.container.inspect(c_id).state.exit_code != 0:
                return True

        return False

    @property
    def stop_code(self) -> int:
        """Returns the exit code from running the `docker compose up` command"""
        # TODO: possibly translate local docker exit cases to ECS stop codes
        if self.run_exception:
            return self.run_exception.return_code

    @property
    def stopped_reason(self) -> str:
        """Returns the stderr from running the `docker compose up` command"""
        if self.run_exception:
            return self.run_exception.stderr


class ECSBackend:
    def __init__(self, pickle_path):
        self.tasks = {}
        self.pickle_path = pickle_path

    def save(self):
        with open(self.pickle_path, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)

    def describe_tasks(self, tasks: List[str], include=None) -> Dict[str, Any]:
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
            if task.is_failure():
                response["failures"].append(
                    Failures(
                        arn=task.task_arn,
                        detail="placeholder-details",
                        # TODO: use exception message instead
                        reason="placeholder-reason",
                    )
                )
                continue
            response["tasks"].append(
                Tasks(
                    lastStatus=task.last_status,
                    createdAt=task.created_at,
                    executionStoppedAt=task.execution_stopped_at,
                    healthStatus=task.task_health_status,
                    # TODO get more precise times for below attributes
                    pullStartedAt=task.created_at,
                    pullStoppedAt=task.created_at,
                    stoppedAt=task.execution_stopped_at,
                    stoppingAt=task.stopping_at,
                    #
                    startedAt=task.started_at,
                    stopCode=task.stop_code,
                    stoppedReason=task.stopped_reason,
                    availabilityZone=task.region,
                    attachments=task.attachments,
                    clusterArn=task.cluster_arn,
                    taskArn=task.task_arn,
                    connectivity="CONNECTED",  # TODO replace placeholder
                    connectivityAt=task.created_at,
                    cpu=task.cpu,
                    desiredStatus="RUNNING",
                    group=task.task_def["family"],
                    memory=task.memory,
                    platformFamily=task.platform_family,
                    taskDefinitionArn=task.task_def_arn,
                    containers=task.containers,
                    **task.request,
                ).dict(exclude_unset=True, exclude_none=True)
            )

        return response

    def run_task(self, **kwargs) -> Dict[str, Any]:
        """
        Returns ECS RunTask response replaced with local docker compose container values

        Arguments:
            task_def_arn: List of task IDs or ARNs
            overrides: ECS task and container overrides
            count: Number of duplicate compose projects to run
        """

        ecs = boto3.client("ecs", endpoint_url=os.environ.get("ECS_ENDPOINT_URL"))
        # use base AWS creds for getting task def
        # so that the task execution role doesn't need extra permissions
        task_def = ecs.describe_task_definition(taskDefinition=kwargs["taskDefinition"])
        task = RunTaskBackend(task_def, **kwargs)
        self.created_at = datetime.timestamp(datetime.now())

        try:
            task.up(
                kwargs["count"], kwargs.get("overrides", {}).get("executionRoleArn")
            )
        except DockerException as e:
            log.debug(f"Exit code {e.return_code} while running {e.docker_command}")
            log.error(e, exc_info=True)
            task.run_exception = e
            task.stopped_at = datetime.timestamp(datetime.now())
            task.stopping_at = datetime.timestamp(datetime.now())
            task.execution_stopped_at = datetime.timestamp(datetime.now())
            task.last_status = "STOPPED"

        self.tasks[task.id] = task

        return self.describe_tasks(tasks=[task.id])

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
    ) -> List[str]:
        arns = []
        for task in self.tasks.values():
            if cluster is not None and task.request["cluster"] != cluster:
                continue
            elif family is not None and task.task_def["family"] != family:
                continue
            elif launch_type is not None and task.request["launchType"] != launch_type:
                continue
            elif service_name is not None and service_name not in task.service_names:
                continue
            elif desired_status is not None and task.last_status != desired_status:
                continue
            elif started_by is not None and task.request.get("startedBy") != started_by:
                continue
            elif (
                container_instance is not None
                and task.container_instance != container_instance
            ):
                continue

            arns.append(task.task_arn)

        return arns[:max_results]
