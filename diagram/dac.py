from diagrams import Cluster, Diagram
from diagrams.aws.compute import ElasticContainerService
from diagrams.aws.management import SystemsManagerParameterStore as ssm
from diagrams.aws.security import SecretsManager as secret
from diagrams.onprem.client import User
from diagrams.onprem.container import Docker
from diagrams.programming.flowchart import Document
from diagrams.programming.framework import Fastapi
from diagrams.programming.language import Python

node_attr = {"fontsize": "25", "height": "10.6", "fontname": "Times bold"}

graph_attr = {
    "fontsize": "60",
    "compund": "True",
    "splines": "spline",
}

edge_attr = {
    "minlen": "2.0",
    "penwidth": "3.0",
    "concentrate": "true",
}

cluster_attr = {
    "fontsize": "40",
}

with Diagram(
    "local-ecs-api",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
    filename="./diagram/local-ecs-api",
    outformat="png",
    show=False,
):
    run_task = Fastapi("/RunTask")
    list_tasks = Fastapi("/ListTasks")
    describe_tasks = Fastapi("/DescribeTasks")
    redirect = Fastapi("/{other paths}")
    endpoints = [run_task, list_tasks, describe_tasks, redirect]
    d = User("\nECS API Request") >> Docker("local-ecs-api") >> endpoints

    with Cluster("Docker Project", graph_attr=cluster_attr):
        docker_proj = Docker("Task Container") - Docker("ECS Endpoint")

    with Cluster("RunTask", graph_attr=cluster_attr):
        compose = Document("Docker Compose")
        r = (
            run_task >> Document("Task Definition") >> compose >> Docker("Compose Up")
        ) >> docker_proj
    compose - [
        Docker("Docker Registry"),
        secret("\nSecret Manager"),
        ssm("\nSystems Manager\nParameter Store"),
    ]
    run_task - Python("ECSBackend")
    list_tasks - Python("ECSBackend")
    describe_tasks - Python("ECSBackend")

    redirect >> ElasticContainerService("\nAWS ECS")
