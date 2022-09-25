# ECS Run Task Local API

Configurable Environment Variables:

`ECS_ENDPOINT_URL`: 
`COMPOSE_DEST`: 
`ECS_NETWORK_NAME`: 

`S3_ENDPOINT_URL`: 
`ECS_ENDPOINT_URL`: 

`IAM_ENDPOINT`: 
`STS_ENDPOINT`: 
`AWS_CONTAINER_CREDENTIALS_RELATIVE_URI`: 

## TODO:

- Create API's for
    - [] RunTask
        - [x] Get task def content from user defined endpoint set via env var
        - [x] Parse task def and convert into docker compose file
        - [x] Run docker compose up with local-ecs-endpoint container service
        - [x] Exclude local ecs endpoint IP from task container ip assignment
        - [x] Formulate RunTaskResponse with docker container metadata
    - [] DescribeTasks
        - [ ] implement test_describe_tasks() integration test

    - [] ListTasks?
