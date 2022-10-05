# ECS Run Task Local API

## Description

Docker image that can be used to to test ECS task locally on local machine. The container will convert the ECS task definition to a local docker compose file, run `docker compose up` and translate local docker attributes into the approriate ECS API response.

## Configurable Environment Variables:

- `ECS_ENDPOINT_URL`: Custom endpoint for ECS requests made within the local API.
- `COMPOSE_DEST`: The directory where task definition conversion to compose files should be stored (defaults to `/tmp`)
- `ECS_NETWORK_NAME`: Name of the local Docker network used for compose services and ECS local endpoint
- `IAM_ENDPOINT`: Custom IAM endpoint the local ECS endpoint container will use for retrieving task AWS credentials
- `STS_ENDPOINT`: Custom STS endpoint the local ECS endpoint container will use for retrieving task AWS credentials

## Example Usage

`docker-compose.yml`:

```
version: '3.4'
services:
  app:
    image: app:latest
    networks:
      local-ecs:
  local-ecs-api:
    image: local-ecs-api:latest
    restart: always
    volumes:
    - /usr/bin/docker:/usr/bin/docker
    - /var/run/docker.sock:/var/run/docker.sock
    ports:
    - 8000:8000
    environment:
    - COMPOSE_DEST
    - IAM_ENDPOINT
    - STS_ENDPOINT
    - ECS_ENDPOINT_URL
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - AWS_DEFAULT_REGION
    networks:
      local-ecs:

networks:
  local-ecs:
    name: local-ecs
    driver: bridge
    ipam:
      driver: default
```

Within the `app` container, AWS ECS API call can be directed to the
`local-ecs-api` container like so:

Python via boto3 client:
```
import boto3
import os

ecs = boto3.client("ecs", endpoint_url="http://local-ecs-network:8000"

ecs.run_task(taskDefinition="arn:aws:ecs:us-west-2:123456789012:task-definition/foo:1")
```

AWS CLI:
```
aws ecs run-task --cluster default --task-definition foo:1 --endpoint-url http://local-ecs-network:8000
```

## RunTask to Docker

The following are step used for converting ECS RunTask requests to local docker compose files

1.

## Response Translation

The following ECS responses will contain attribute that reference the local docker compose project

`RunTask`
```
{
   "failures": [ 
      { 
         "arn": <docker>,
         "detail": <docker compose up stderr>,
         "reason": <docker compose up stderr translated to ecs reason>
      }
   ],
   "tasks": [ 
      { 
         "attachments": [ 
            { 
               "details": [ 
                  { 
                     "name": "string",
                     "value": "string"
                  }
               ],
               "id": "string",
               "status": "string",
               "type": "string"
            }
         ],
         "attributes": [ 
            { 
               "name": "string",
               "targetId": "string",
               "targetType": "string",
               "value": "string"
            }
         ],
         "availabilityZone": <AWS region parsed from task definition ARN>,
         "capacityProviderName": "string",
         "clusterArn": <uses `cluster` argument from RunTask request>,
         "connectivity": "string",
         "connectivityAt": number,
         "containerInstanceArn": "string",
         "containers": [ 
            { 
               "containerArn": <uses local docker container ID>,
               "cpu": <gets from task definition or RunTask overrides>,
               "exitCode": <gets from docker container inspect>,
               "gpuIds": [ "string" ],
               "healthStatus": <gets from docker container inspect>,
               "image": <gets from docker container inspect>,
               "imageDigest": <gets from docker container inspect>,
               "lastStatus": <gets from docker container inspect>,
               "managedAgents": [ 
                  { 
                     "lastStartedAt": number,
                     "lastStatus": "string",
                     "name": "string",
                     "reason": "string"
                  }
               ],
               "memory": <gets from task definition or RunTask overrides>,
               "memoryReservation": "string",
               "name": <gets from docker container inspect>,
               "networkBindings": [ 
                  { 
                     "bindIP": "string",
                     "containerPort": number,
                     "hostPort": number,
                     "protocol": "string"
                  }
               ],
               "networkInterfaces": [ 
                  { 
                     "attachmentId": "string",
                     "ipv6Address": "string",
                     "privateIpv4Address": "string"
                  }
               ],
               "reason": <gets from docker container inspect>,
               "runtimeId": <gets from docker container inspect>,
               "taskArn": <gets from docker container inspect>,
            }
         ],
         "cpu": <gets from task definition or RunTask overrides>,
         "createdAt": number,
         "desiredStatus": "string",
         "enableExecuteCommand": <gets from RunTask request>,
         "ephemeralStorage": { 
            "sizeInGiB": number
         },
         "executionStoppedAt": number,
         "group": "string",
         "healthStatus": <see local_ecs_api.models.task_health_status()>,
         "inferenceAccelerators": [ 
            { 
               "deviceName": "string",
               "deviceType": "string"
            }
         ],
         "lastStatus": <gets from docker compose ps>,
         "launchType": <gets from RunTask request>,
         "memory": <gets from task definition or RunTask overrides>,
         "overrides": <gets from RunTask request>,
         "platformFamily": <gets from running docker compose ps on local-ecs-endpoint's project>,
         "platformVersion": "string",
         "pullStartedAt": number,
         "pullStoppedAt": number,
         "startedAt": number,
         "startedBy": <gets from RunTask request>,
         "stopCode": <docker compose up return code translated into ECS StopCode>,
         "stoppedAt": number,
         "stoppedReason": <TODO>,
         "stoppingAt": number,
         "tags": <gets from RunTask request>,
         "taskArn": <interpolates docker compose project ID as task ID>,
         "taskDefinitionArn": <gets from RunTask request>,
         "version": number
      }
   ]
}
```
`DescribeTask`
(same as `RunTask`)

`ListTasks`



## TODO

- [ ] Handle RunTask request that fail on pulling container images
    - associated container should not be in failures attribute
- [ ] Add the following to the to DescribeTasksResponse
    - [ ] `attributes`
    - [ ] `capacityProviderName` (remove for Fargate tasks)
    - [ ] `containerInstanceArn` (remove for Fargate tasks)
    - [ ] `ephemeralStorage`
    - [ ] `inferenceAccelerators`
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
    - if launchType == "FARGATE" then ensure capacityProviderStrategy is not set
- add group attribute to describeTasks response


