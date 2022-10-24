# ECS Run Task Local API

Docker image that can be used to test ECS tasks on a local machine. The container will convert the ECS task definition to a docker-compose file, run `docker compose up` and translate docker attributes into the appropriate ECS API response.

## Configurable Environment Variables:

- `ECS_ENDPOINT_URL`: Custom endpoint for ECS requests made within the local API. This endpoint URL will be used for redirecting any ECS requests that are not supported by this API and for retrieving the task definition to be converted into docker compose files.
- `COMPOSE_DEST`: The directory where task definition conversion to compose files should be stored (defaults to `/tmp`)
- `IAM_ENDPOINT`: Custom IAM endpoint the local ECS endpoint container will use for retrieving task AWS credentials
- `STS_ENDPOINT`: Custom STS endpoint used for:
   -  Retrieving AWS execution role credentials within local-ecs-api container
   -  Retrieving AWS task credentials within local ECS endpoint container
- `SECRET_MANAGER_ENDPOINT_URL`: Custom Secret Manager endpoint used to retrieve secrets specified within the task definition to load into containers
- `SSM_ENDPOINT_URL`: Custom Systems Manager endpoint used to retrieve secrets specified within the task definition to load into containers
- `AWS_ACCESS_KEY_ID`: AWS access key used for assuming task execution role and getting task definition
- `AWS_SECRET_ACCESS_KEY`: AWS secret access key used for assuming task execution role and getting task definition


## Credentials Requirements

The local-ecs-api container somewhat simulates the ECS container agent used for running ECS tasks. This means that the container needs the appropriate AWS credentials to assume any ECS task execution roles that are given. The AWS credentials can be passed to the container via:

1. Environment variables

`docker-compose.yml`
```
version: '3.4'
services:
  local-ecs-api:
    image: local-ecs-api:latest
    environment:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
```

2. AWS profile

`docker-compose.yml`
```
version: '3.4'
services:
  local-ecs-api:
    image: local-ecs-api:latest
    environment:
      - AWS_PROFILE=${AWS_PROFILE}
    volumes:
      - ~/.aws/:/root/.aws:ro
```

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
    - SECRET_MANAGER_ENDPOINT_URL
    - SSM_ENDPOINT_URL
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

Within the `app` container, AWS ECS API calls can be directed to the
`local-ecs-api` container like so:

Python via boto3 client:
```
import boto3
import os

ecs = boto3.client("ecs", endpoint_url="http://local-ecs-api:8000"

ecs.run_task(taskDefinition="arn:aws:ecs:us-west-2:123456789012:task-definition/foo:1")
```

AWS CLI:
```
aws ecs run-task --cluster default --task-definition foo:1 --endpoint-url http://local-ecs-api:8000
```

## Design
 
![Diagram](./diagram/local-ecs-api.png)

## Response Translation

The following ECS responses will contain attributes that reference the local docker compose project

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
         "stopCode": <docker compose up return code>,
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


- add heredocs to converters.py
- add heredocs to main.py
- add heredocs to models.py
- create diagram for RunTask functionality
- add save() to RunTask function for saving to .pickle file



- container needs to have the following permission:
   ecs:describetasks on all resources
   - create predefined ECS local endpoint docker compose files for
      - AWS env creds
      - AWS profile
   - create ENV var to specify shared volume mount to add user-defined override compose files for endpoint or tasks

- create async background task to monitor when ecs task containers stop. if container stopped, gather container metadata and then remove container? ensures that subsequent RunTask calls will not use the stopped container but an entirely new one

see if coupling local endpoint servicce to task will cause any issue
if not have it where user can define compose override files that contain the proper filename suffix
then they can override the task's local ecs endpoint config with the proper AWS creds to retreive creds
for tasks

create env vars for AWS cred mount

- ECS_ENDPOINT_AWS_PROFILE
- ECS_ENDPOINT_AWS_CREDS_HOST_PATH

- ECS_ENDPOINT_AWS_ACCESS_KEY_ID
- ECS_ENDPOINT_AWS_REGION
- ECS_ENDPOINT_AWS_SECRET_ACCESS_KEY

1. if above env vars are present in local-ecs-api, create independent docker volume for mounting AWS creds from host
2. then use pre-defined local-ecs-endpoint compose file that has the external mount defined

1. or use aws environment variable passed
