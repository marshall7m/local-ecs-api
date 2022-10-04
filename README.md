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
