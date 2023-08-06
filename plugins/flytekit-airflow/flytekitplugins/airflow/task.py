import typing
from dataclasses import dataclass
from typing import Any, Dict, Optional, Type

import cloudpickle
import jsonpickle
from airflow import DAG
from airflow.models import BaseOperator
from airflow.sensors.base import BaseSensorOperator

from flytekit import FlyteContextManager
from flytekit.configuration import SerializationSettings
from flytekit.core.base_task import PythonTask
from flytekit.core.interface import Interface
from flytekit.extend.backend.base_agent import AsyncAgentExecutorMixin


@dataclass
class AirflowConfig(object):
    task_module: str
    task_name: str
    task_config: typing.Dict[str, Any]


class AirflowTask(AsyncAgentExecutorMixin, PythonTask[AirflowConfig]):
    _TASK_TYPE = "airflow"

    def __init__(
        self,
        name: str,
        query_template: str,
        task_config: Optional[AirflowConfig],
        inputs: Optional[Dict[str, Type]] = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            task_config=task_config,
            query_template=query_template,
            interface=Interface(inputs=inputs or {}),
            task_type=self._TASK_TYPE,
            **kwargs,
        )

    def get_custom(self, settings: SerializationSettings) -> Dict[str, Any]:
        return {"task_config_pkl": cloudpickle.dumps(self.task_config)}


def _flyte_operator(*args, **kwargs):
    cls = args[0]
    if FlyteContextManager.current_context().user_space_params.get_original_task:
        return object.__new__(cls)
    config = AirflowConfig(task_module=cls.__module__, task_name=cls.__name__, task_config=kwargs)
    t = AirflowTask(name=cls.__name__, query_template="", task_config=config, original_new=cls.__new__)
    return t()


def _flyte_xcom_push(*args, **kwargs):
    FlyteContextManager.current_context().user_space_params.xcom_data = kwargs


params = FlyteContextManager.current_context().user_space_params
params.builder().add_attr("GET_ORIGINAL_TASK", False).add_attr("XCOM_DATA", {}).build()

BaseOperator.__new__ = _flyte_operator
BaseOperator.xcom_push = _flyte_xcom_push
BaseSensorOperator.dag = DAG(dag_id="flyte_dag")