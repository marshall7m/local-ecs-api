import uuid

task_defs = {
    "fast_fail": {
        "containerDefinitions": [
            {
                "name": "fast_fail",
                "command": [
                    "/bin/sh",
                    "fail",
                ],
                "cpu": 1,
                "essential": True,
                "image": "busybox",
                "memory": 10,
            }
        ],
        "family": "fast_fail",
        "taskRoleArn": "arn:aws:iam::12345679012:role/mock-task",
    },
    "essential_success": {
        "containerDefinitions": [
            {
                "name": "essential_success",
                "command": [
                    "sleep",
                    "5",
                ],
                "cpu": 10,
                "essential": True,
                "image": "busybox",
                "memory": 10,
            },
        ],
        "family": "essential_success",
        "taskRoleArn": "arn:aws:iam::12345679012:role/mock-task",
    },
    "fast_success": {
        "containerDefinitions": [
            {
                "name": "fast_success",
                "command": ["/bin/sh"],
                "cpu": 1,
                "essential": True,
                "image": "busybox",
                "memory": 10,
            },
        ],
        "family": "fast_success",
        "taskRoleArn": "arn:aws:iam::12345679012:role/mock-task",
    },
    "invalid_img": {
        "containerDefinitions": [
            {
                "name": "invalid_img",
                "command": ["/bin/sh"],
                "cpu": 1,
                "essential": True,
                "image": f"invalid:{uuid.uuid4()}",
                "memory": 10,
            },
        ],
        "family": "invalid_img",
        "taskRoleArn": "arn:aws:iam::12345679012:role/mock-task",
    },
}
