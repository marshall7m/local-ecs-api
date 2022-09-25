
from local_ecs_api.converters import DockerTask
import pytest

@pytest.mark.parametrize("task_def,overrides,expected_task_def", [
    pytest.param(
        {
            "taskDefinition": {
                "taskDefinitionArn": "arn:ecs:123456789012:us-west-2:task-def/foo",
                "containerDefinitions": [
                    {
                        "name": "A",
                        "environment": [
                            {
                                "key": "foo",
                                "value": "baz"
                            },
                            {
                                "key": "1",
                                "value": "2"
                            }
                        ]
                    }
                ]
            }
        },
        {
            "containerOverrides": [
                {
                    "name": "A",
                    "environment": [
                        {
                            "key": "foo",
                            "value": "bar"
                        }
                    ]
                }
            ]
        },
        {
            "containerDefinitions": [
                {
                    "name": "A",
                    "environment": [
                        {
                            "key": "foo",
                            "value": "bar"
                        },
                        {
                            "key": "1",
                            "value": "2"
                        }
                    ]

                }
            ],
            "taskDefinitionArn": "arn:ecs:123456789012:us-west-2:task-def/foo",
        }
    )
])
def test_merge_overrides(task_def, overrides, expected_task_def):
    task = DockerTask(task_def)

    actual_task_def = task.merge_overrides(task.task_def, overrides)
    assert actual_task_def == expected_task_def