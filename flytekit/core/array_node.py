import math
from typing import Any, List, Optional, Set, Tuple, Union

from flytekit.core import interface as flyte_interface
from flytekit.core.context_manager import ExecutionState, FlyteContext
from flytekit.core.interface import transform_interface_to_list_interface, transform_interface_to_typed_interface
from flytekit.core.launch_plan import LaunchPlan
from flytekit.core.node import Node
from flytekit.core.promise import (
    Promise,
    VoidPromise,
    flyte_entity_call_handler,
    translate_inputs_to_literals,
)
from flytekit.core.task import TaskMetadata
from flytekit.loggers import logger
from flytekit.models import literals as _literal_models
from flytekit.models.core import workflow as _workflow_model
from flytekit.models.literals import Literal, LiteralCollection, Scalar


class ArrayNode:
    def __init__(
        self,
        target: LaunchPlan,
        concurrency: Optional[int] = None,
        min_successes: Optional[int] = None,
        min_success_ratio: Optional[float] = None,
        bound_inputs: Optional[Set[str]] = None,
        execution_version: Optional[int] = None,
        metadata: Optional[Union[_workflow_model.NodeMetadata, TaskMetadata]] = None,
    ):
        """
        :param target: The target Flyte entity to map over
        :param concurrency: If specified, this limits the number of mapped tasks than can run in parallel to the given batch
            size. If the size of the input exceeds the concurrency value, then multiple batches will be run serially until
            all inputs are processed. If set to 0, this means unbounded concurrency. If left unspecified, this means the
            array node will inherit parallelism from the workflow
        :param min_success_ratio: If specified, this determines the minimum fraction of total jobs which can complete
            successfully before terminating this task and marking it successful.
        :param min_successes: If specified, an absolute number of the minimum number of successful completions of subtasks.
            As soon as the criteria is met, the array job will be marked as successful and outputs will be computed.
        """
        self.target = target
        self._concurrency = concurrency
        self._min_successes = min_successes
        self._min_success_ratio = min_success_ratio
        self._execution_version = execution_version
        self.id = target.name

        n_outputs = len(self.target.python_interface.outputs)
        if n_outputs > 1:
            raise ValueError("Only tasks with a single output are supported in map tasks.")

        self._bound_inputs: Set[str] = bound_inputs or set(bound_inputs) if bound_inputs else set()

        output_as_list_of_optionals = min_success_ratio is not None and min_success_ratio != 1 and n_outputs == 1
        collection_interface = transform_interface_to_list_interface(
            self.target.python_interface, self._bound_inputs, output_as_list_of_optionals
        )
        self._collection_interface = collection_interface

        self.metadata = None
        if isinstance(target, LaunchPlan):
            if self._execution_version is None:
                self._execution_version = 1
            if self._execution_version != 1:
                raise ValueError("Only execution version 1 is supported for LaunchPlans.")
            if metadata:
                if isinstance(metadata, _workflow_model.NodeMetadata):
                    self.metadata = metadata
                else:
                    raise Exception("Invalid metadata for LaunchPlan. Should be NodeMetadata.")
        else:
            raise Exception("Only LaunchPlans are supported for now.")

    def construct_node_metadata(self) -> _workflow_model.NodeMetadata:
        # Part of SupportsNodeCreation interface
        # TODO - include passed in metadata
        return _workflow_model.NodeMetadata(name=self.target.name)

    @property
    def name(self) -> str:
        # Part of SupportsNodeCreation interface
        return self.target.name

    @property
    def python_interface(self) -> flyte_interface.Interface:
        # Part of SupportsNodeCreation interface
        return self._collection_interface

    @property
    def bindings(self) -> List[_literal_models.Binding]:
        return []

    @property
    def upstream_nodes(self) -> List[Node]:
        return []

    @property
    def flyte_entity(self) -> Any:
        return self.target

    def local_execute(self, ctx: FlyteContext, **kwargs) -> Union[Tuple[Promise], Promise, VoidPromise]:
        outputs_expected = True
        if not self.python_interface.outputs:
            outputs_expected = False

        mapped_entity_count = 0
        for k in self.python_interface.inputs.keys():
            if k not in self._bound_inputs:
                v = kwargs[k]
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], self.target.python_interface.inputs[k]):
                    mapped_entity_count = len(v)
                    break
                else:
                    raise ValueError(
                        f"Expected a list of {self.target.python_interface.inputs[k]} but got {type(v)} instead."
                    )

        failed_count = 0
        min_successes = mapped_entity_count
        if self._min_successes:
            min_successes = self._min_successes
        elif self._min_success_ratio:
            min_successes = math.ceil(min_successes * self._min_success_ratio)

        literals = []
        for i in range(mapped_entity_count):
            single_instance_inputs = {}
            for k in self.python_interface.inputs.keys():
                if k not in self._bound_inputs:
                    single_instance_inputs[k] = kwargs[k][i]
                else:
                    single_instance_inputs[k] = kwargs[k]

            # translate Python native inputs to Flyte literals
            typed_interface = transform_interface_to_typed_interface(self.target.python_interface)
            literal_map = translate_inputs_to_literals(
                ctx,
                incoming_values=single_instance_inputs,
                flyte_interface_types={} if typed_interface is None else typed_interface.inputs,
                native_types=self.target.python_interface.inputs,
            )
            kwargs_literals = {k1: Promise(var=k1, val=v1) for k1, v1 in literal_map.items()}

            try:
                output = self.target.__call__(**kwargs_literals)
                if outputs_expected:
                    literals.append(output.val)

            except Exception as exc:
                if outputs_expected:
                    literal_with_none = Literal(scalar=Scalar(none_type=_literal_models.Void()))
                    literals.append(literal_with_none)
                    failed_count += 1
                    if mapped_entity_count - failed_count < min_successes:
                        logger.error("The number of successful tasks is lower than the minimum ratio")
                        raise exc

        if outputs_expected:
            return Promise(var="o0", val=Literal(collection=LiteralCollection(literals=literals)))
        return VoidPromise(self.name)

    def local_execution_mode(self):
        return ExecutionState.Mode.LOCAL_TASK_EXECUTION

    @property
    def min_success_ratio(self) -> Optional[float]:
        return self._min_success_ratio

    @property
    def min_successes(self) -> Optional[int]:
        return self._min_successes

    @property
    def concurrency(self) -> Optional[int]:
        return self._concurrency

    @property
    def execution_version(self) -> Optional[int]:
        return self._execution_version


def array_node(
    target: Union[LaunchPlan],
    concurrency: Optional[int] = None,
    min_success_ratio: Optional[float] = None,
    min_successes: Optional[int] = None,
    **kwargs,
):
    """
    Map tasks that maps over tasks and other Flyte entities
    Args:
    :param target: The target Flyte entity to map over
    :param concurrency: If specified, this limits the number of mapped tasks than can run in parallel to the given batch
        size. If the size of the input exceeds the concurrency value, then multiple batches will be run serially until
        all inputs are processed. If set to 0, this means unbounded concurrency. If left unspecified, this means the
        array node will inherit parallelism from the workflow
    :param min_success_ratio: If specified, this determines the minimum fraction of total jobs which can complete
        successfully before terminating this task and marking it successful.
    :param min_successes: If specified, an absolute number of the minimum number of successful completions of subtasks.
        As soon as the criteria is met, the array job will be marked as successful and outputs will be computed.
    """
    if not isinstance(target, LaunchPlan):
        raise ValueError("Only LaunchPlans are supported for now.")

    node = ArrayNode(target, concurrency, min_successes, min_success_ratio)

    def callable_entity(**inner_kwargs):
        combined_kwargs = {**kwargs, **inner_kwargs}
        return flyte_entity_call_handler(node, **combined_kwargs)

    return callable_entity
