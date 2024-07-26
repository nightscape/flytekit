from dataclasses import dataclass
from typing import Optional

import anyscale
from anyscale.job.models import JobConfig

from flytekit.extend.backend.base_agent import AgentRegistry, AsyncAgentBase, Resource, ResourceMeta
from flytekit.extend.backend.utils import convert_to_flyte_phase
from flytekit.models.literals import LiteralMap
from flytekit.models.task import TaskTemplate


@dataclass
class AnyscaleJobMetadata(ResourceMeta):
    job_id: str


class AnyscaleAgent(AsyncAgentBase):
    name = "Anyscale Agent"

    def __init__(self):
        super().__init__(task_type_name="anyscale", metadata_type=AnyscaleJobMetadata)

    async def create(
        self, task_template: TaskTemplate, inputs: Optional[LiteralMap] = None, **kwargs
    ) -> AnyscaleJobMetadata:
        print("task_template", task_template)
        container = task_template.container
        config = JobConfig(
            name="flyte-rag",
            entrypoint=" ".join(container.args),
            working_dir="/Users/kevin/git/flytekit/flyte-example/anyscale_union",
            max_retries=1,
            compute_config="flyte-rag",
        )

        job_id = anyscale.job.submit(config)

        return AnyscaleJobMetadata(job_id=job_id)

    async def get(self, resource_meta: AnyscaleJobMetadata, **kwargs) -> Resource:
        cur_phase = convert_to_flyte_phase(anyscale.job.status(id=resource_meta.job_id).state.value)

        return Resource(phase=cur_phase, message=None, log_links=None)

    async def delete(self, resource_meta: AnyscaleJobMetadata, **kwargs):
        anyscale.job.terminate(id=resource_meta.job_id)


AgentRegistry.register(AnyscaleAgent())
