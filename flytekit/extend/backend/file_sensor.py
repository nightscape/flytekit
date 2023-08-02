import asyncio
from typing import Optional

import fsspec
import grpc
from fsspec.utils import get_protocol

from flytekit.configuration import DataConfig
from flytekit.core.data_persistence import s3_setup_args
from flytekit.core.sensor_task import FileSensorConfig
from flytekit.extend.backend.base_agent import AgentRegistry
from flytekit.extend.backend.base_sensor import SensorBase
from flytekit.models.literals import LiteralMap
from flytekit.models.task import TaskTemplate


class FileSensor(SensorBase):
    def __init__(self):
        super().__init__(task_type="file_sensor")

    async def poke(self, cfg: FileSensorConfig) -> bool:
        path = cfg.path
        protocol = get_protocol(path)
        kwargs = {}
        if get_protocol(path):
            kwargs = s3_setup_args(DataConfig.auto().s3, anonymous=False)
        fs = fsspec.filesystem(protocol, **kwargs)
        return await asyncio.to_thread(fs.exists, path)

    async def extract(
        self, context: grpc.ServicerContext, task_template: TaskTemplate, inputs: Optional[LiteralMap] = None
    ) -> FileSensorConfig:
        return FileSensorConfig(**task_template.custom)


AgentRegistry.register(FileSensor())
