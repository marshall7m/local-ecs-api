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
    cluster: Optional[str]
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


class DescribeTasksResponse(BaseModel):
    failures: List[Failures] = List
    tasks: List[Tasks] = List


class DescribeTasksRequest(BaseModel):
    failures: List[Failures] = List
    tasks: List[Tasks] = List


class ListTasksRequest(BaseModel):
    pass
