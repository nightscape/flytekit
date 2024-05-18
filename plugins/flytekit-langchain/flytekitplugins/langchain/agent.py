from typing import Any, Optional

import jsonpickle
from flyteidl.core.execution_pb2 import TaskExecution
from flytekitplugins.langchain.task import _get_langchain_instance

from flytekit import FlyteContextManager
from flytekit.core.type_engine import TypeEngine
from flytekit.extend.backend.base_agent import AgentRegistry, Resource, SyncAgentBase
from flytekit.models.literals import LiteralMap
from flytekit.models.task import TaskTemplate
from flytekit.types.pickle import FlytePickle


class LangChainAgent(SyncAgentBase):
    """
    It is used to run Airflow tasks. It is registered as an agent in the AgentRegistry.
    There are three kinds of Airflow tasks: AirflowOperator, AirflowSensor, and AirflowHook.

    Sensor is always invoked in get method. Calling get method to check if the certain condition is met.
    For example, FileSensor is used to check if the file exists. If file doesn't exist, agent returns
    RUNNING status, otherwise, it returns SUCCEEDED status.

    Hook is a high-level interface to an external platform that lets you quickly and easily talk to
     them without having to write low-level code that hits their API or uses special libraries. For example,
     SlackHook is used to send messages to Slack. Therefore, Hooks are also invoked in get method.
    Note: There is no running state for Hook. It is either successful or failed.

    Operator is invoked in create method. Flytekit will always set deferrable to True for Operator. Therefore,
    `operator.execute` will always raise TaskDeferred exception after job is submitted. In the get method,
    we create a trigger to check if the job is finished.
    Note: some of the operators are not deferrable. For example, BeamRunJavaPipelineOperator, BeamRunPythonPipelineOperator.
     In this case, those operators will be converted to AirflowContainerTask and executed in the pod.
    """

    name = "LangChain Agent"

    def __init__(self):
        super().__init__(task_type_name="langchain")

    async def do(
        self,
        task_template: TaskTemplate,
        inputs: Optional[LiteralMap] = None,
    ) -> Resource:
        langchain_obj = jsonpickle.decode(task_template.custom["task_config_pkl"])
        langchain_instance = _get_langchain_instance(langchain_obj)
        ctx = FlyteContextManager.current_context()
        input_python_value = TypeEngine.literal_map_to_kwargs(ctx, inputs, {"input": Any})
        message = input_python_value["input"]
        message = langchain_instance.invoke(message)
        return Resource(
            phase=TaskExecution.SUCCEEDED,
            outputs=LiteralMap(literals={"o0": TypeEngine.to_literal(ctx, message, Any, FlytePickle)}),
        )


AgentRegistry.register(LangChainAgent())