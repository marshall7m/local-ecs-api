from pydantic import BaseModel
from typing import List, Optional

# TODO uppercase class names


class capacityProviderStrategy(BaseModel):
    base: int
    capacityProvider: str
    weight: int


class awsvpcConfiguration(BaseModel):
    assignPublicIp: str
    securityGroups: List[str]
    subnets: List[str]


class networkConfiguration(BaseModel):
    awsvpcConfiguration: awsvpcConfiguration


class resourceRequirements(BaseModel):
    type: str
    value: str


class environment(BaseModel):
    name: str
    value: str


class environmentFiles(BaseModel):
    type: str
    value: str


class containerOverrides(BaseModel):
    command: List[str]
    cpu: int
    environment: List[environment]
    environmentFiles: List[environmentFiles]
    memory: int
    memoryReservation: int
    name: str
    resourceRequirements: List[resourceRequirements]


class ephemeralStorage(BaseModel):
    sizeInGiB: int


class deviceName(BaseModel):
    deviceName: str
    deviceType: str


class placementConstraints(BaseModel):
    expression: str
    type: str


class placementStrategy(BaseModel):
    field: str
    type: str


class tags(BaseModel):
    key: str
    type: str


class inferenceAccelerators(BaseModel):
    deviceName: str
    deviceType: str


class overrides(BaseModel):
    containerOverrides: Optional[List[containerOverrides]]
    cpu: str
    ephemeralStorage: ephemeralStorage
    executionRoleArn: str
    inferenceAcceleratorOverrides: List[inferenceAccelerators]
    memory: str
    taskRoleArn: str


class RunTaskRequest(BaseModel):
    capacityProviderStrategy: Optional[List[capacityProviderStrategy]]
    cluster: Optional[str]
    count: Optional[int] = 1
    enableECSManagedTags: Optional[bool]
    enableExecuteCommand: Optional[bool]
    group: Optional[str]
    launchType: Optional[str]
    networkConfiguration: Optional[awsvpcConfiguration]
    overrides: Optional[overrides]
    placementConstraints: Optional[List[placementConstraints]]
    placementStrategy: Optional[List[placementStrategy]]
    platformVersion: Optional[str]
    propagateTags: Optional[str]
    propagateTags: Optional[str]
    referenceId: Optional[str]
    startedBy: Optional[str]
    tags: Optional[List[tags]]
    taskDefinition: str


class failures(BaseModel):
    arn: str
    detail: str
    reason: str


class details(BaseModel):
    name: str
    value: str


class attributes(BaseModel):
    name: str
    targetId: str
    targetType: str
    value: str


class attachments(BaseModel):
    id: str
    status: str
    type: str
    defails: List[details]


class managedAgents(BaseModel):
    lastStartedAt: int
    lastStatus: str
    name: str
    reason: str


class networkBindings(BaseModel):
    bindIP: str
    containerPort: int
    hostPort: int
    protocol: str


class networkInterfaces(BaseModel):
    attachmentId: str
    ipv6Address: str
    privateIpv4Address: str


class containers(BaseModel):
    containerArn: str
    cpu: str
    exitCode: int
    gpuIds: List[str]
    healthStatus: str
    image: str
    imageDigest: str
    lastStatus: str
    managedAgents: List[managedAgents]
    memory: str
    memoryReservation: str
    name: str
    networkBindings: List[networkBindings]
    networkInterfaces: List[networkInterfaces]
    reason: str
    runtimeId: str
    taskArn: str


class tasks(BaseModel):
    attachments: List[attachments]
    attributes: List[attributes]
    availabilityZone: str
    capacityProviderName: str
    clusterArn: str
    connectivity: str
    connectivityAt: int
    containerInstanceArn: str
    cpu: str
    createdAt: int
    desiredStatus: str
    enableExecuteCommand: bool
    executionStoppedAt: int
    group: str
    healthStatus: str
    lastStatus: str
    launchType: str
    memory: str
    platformFamily: str
    platformVersion: str
    pullStartedAt: int
    pullStoppedAt: int
    startedAt: int
    startedBy: str
    stopCode: str
    stoppedAt: int
    stoppedReason: str
    stoppingAt: int
    taskArn: str
    taskDefinitionArn: str
    version: int
    containers: List[containers]
    ephemeralStorage: ephemeralStorage
    inferenceAccelerators: List[inferenceAccelerators]
    overrides: List[overrides]
    tags: List[tags]


class RunTaskResponse(BaseModel):
    failures: List[failures] = List
    tasks: List[tasks] = List


class DescribeTasksRequest(BaseModel):
    pass


class ListTasksRequest(BaseModel):
    pass
