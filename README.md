# ECS Run Task Local API

## Description

## Configurable Environment Variables:

- `ECS_ENDPOINT_URL`: Custom endpoint for ECS requests made within the local API.
- `COMPOSE_DEST`: The directory where task definition conversion to compose files should be stored (defaults to `/tmp`)
- `ECS_NETWORK_NAME`: Name of the local Docker network used for compose services and ECS local endpoint
- `IAM_ENDPOINT`: Custom IAM endpoint the local ECS endpoint container will use for retrieving task AWS credentials
- `STS_ENDPOINT`: Custom STS endpoint the local ECS endpoint container will use for retrieving task AWS credentials

## Example Usage

Testing compose file:


## TODO

- [ ] Handle RunTask request that fail on pulling container images
    - associated container should not be in failures attribute
- [ ] Add the following to the to DescribeTasksResponse
    - [ ] `attributes`
    - [ ] `capacityProviderName` (remove for Fargate tasks)
    - [ ] `containerInstanceArn` (remove for Fargate tasks)
    - [ ] `cpu`
    - [ ] `ephemeralStorage`
    - [ ] `group`
    - [ ] `inferenceAccelerators`
    - [ ] `lastStatus`
    - [ ] `launchType`
    - [ ] `memory`
    - [ ] `overrides`
    - [ ] `platformVersion`
    - [ ] `startedBy` (remove if RunTask request doesn't include attribute)
    - [ ] `stoppedReason`
    - [ ] `version`
- [ ] add to `attachments` response attr
- Add values for attr when task is still running:
    - [ ] `stop_code`
    - [ ] `stopped_reason`
    - [ ] `execution_stopped_at`
    - [ ] `stopping_at`

- add pydantic validation for request that are fargate
    - require cpu, memory, etc
    
- add group attribute to describeTasks response