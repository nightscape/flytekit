import pytest
from flytekitplugins.awssagemaker import (
    SagemakerDeleteEndpointConfigTask,
    SagemakerDeleteEndpointTask,
    SagemakerDeleteModelTask,
    SagemakerEndpointConfigTask,
    SagemakerEndpointTask,
    SagemakerInvokeEndpointTask,
    SagemakerModelTask,
)

from flytekit import kwtypes
from flytekit.configuration import Image, ImageConfig, SerializationSettings


@pytest.mark.parametrize(
    "name,config,service,method,inputs,container_image,no_of_inputs,no_of_outputs,region,task",
    [
        (
            "sagemaker_model",
            {
                "ModelName": "{inputs.model_name}",
                "PrimaryContainer": {
                    "Image": "{container.image}",
                    "ModelDataUrl": "{inputs.model_data_url}",
                },
                "ExecutionRoleArn": "{inputs.execution_role_arn}",
            },
            "sagemaker",
            "create_model",
            kwtypes(model_name=str, model_data_url=str, execution_role_arn=str),
            "1234567890.dkr.ecr.us-east-2.amazonaws.com/sagemaker-xgboost",
            3,
            1,
            "us-east-2",
            SagemakerModelTask,
        ),
        (
            "sagemaker_endpoint_config",
            {
                "EndpointConfigName": "{inputs.endpoint_config_name}",
                "ProductionVariants": [
                    {
                        "VariantName": "variant-name-1",
                        "ModelName": "{inputs.model_name}",
                        "InitialInstanceCount": 1,
                        "InstanceType": "ml.m4.xlarge",
                    },
                ],
                "AsyncInferenceConfig": {"OutputConfig": {"S3OutputPath": "{inputs.s3_output_path}"}},
            },
            "sagemaker",
            "create_endpoint_config",
            kwtypes(endpoint_config_name=str, model_name=str, s3_output_path=str),
            None,
            3,
            1,
            "us-east-2",
            SagemakerEndpointConfigTask,
        ),
        (
            "sagemaker_endpoint",
            {
                "EndpointName": "{inputs.endpoint_name}",
                "EndpointConfigName": "{inputs.endpoint_config_name}",
            },
            None,
            None,
            kwtypes(endpoint_name=str, endpoint_config_name=str),
            None,
            2,
            1,
            "us-east-2",
            SagemakerEndpointTask,
        ),
        (
            "sagemaker_delete_endpoint",
            {"EndpointName": "{inputs.endpoint_name}"},
            "sagemaker",
            "delete_endpoint",
            kwtypes(endpoint_name=str),
            None,
            1,
            0,
            "us-east-2",
            SagemakerDeleteEndpointTask,
        ),
        (
            "sagemaker_delete_endpoint_config",
            {"EndpointConfigName": "{inputs.endpoint_config_name}"},
            "sagemaker",
            "delete_endpoint_config",
            kwtypes(endpoint_config_name=str),
            None,
            1,
            0,
            "us-east-2",
            SagemakerDeleteEndpointConfigTask,
        ),
        (
            "sagemaker_delete_model",
            {"ModelName": "{inputs.model_name}"},
            "sagemaker",
            "delete_model",
            kwtypes(model_name=str),
            None,
            1,
            0,
            "us-east-2",
            SagemakerDeleteModelTask,
        ),
        (
            "sagemaker_invoke_endpoint",
            {
                "EndpointName": "{inputs.endpoint_name}",
                "InputLocation": "s3://sagemaker-agent-xgboost/inference_input",
            },
            "sagemaker-runtime",
            "invoke_endpoint_async",
            kwtypes(endpoint_name=str),
            None,
            1,
            1,
            "us-east-2",
            SagemakerInvokeEndpointTask,
        ),
    ],
)
def test_sagemaker_task(
    name,
    config,
    service,
    method,
    inputs,
    container_image,
    no_of_inputs,
    no_of_outputs,
    region,
    task,
):
    if container_image:
        sagemaker_task = task(
            name=name,
            config=config,
            region=region,
            inputs=inputs,
            container_image=container_image,
        )
    else:
        sagemaker_task = task(
            name=name,
            config=config,
            region=region,
            inputs=inputs,
        )

    assert len(sagemaker_task.interface.inputs) == no_of_inputs
    assert len(sagemaker_task.interface.outputs) == no_of_outputs

    default_img = Image(name="default", fqn="test", tag="tag")
    serialization_settings = SerializationSettings(
        project="project",
        domain="domain",
        version="123",
        image_config=ImageConfig(default_image=default_img, images=[default_img]),
        env={},
    )

    retrieved_settings = sagemaker_task.get_custom(serialization_settings)

    assert retrieved_settings.get("service") == service
    assert retrieved_settings["config"] == config
    assert retrieved_settings["region"] == region
    assert retrieved_settings.get("method") == method