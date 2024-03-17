from typing import Callable, Optional
import multiprocessing
import inspect
import flytekit
import nbformat as nbf
from flytekit.core.context_manager import FlyteContextManager
from flytekitplugins.flyteinteractive.utils import execute_command
from flytekit.loggers import logger
from flytekit.core.utils import ClassDecorator

from ..constants import MAX_IDLE_SECONDS
from .jupyter_constants import EXAMPLE_JUPYTER_NOTEBOOK_NAME


def write_example_notebook(task_function: Optional[Callable], notebook_dir: str):
    """
    Create an example notebook with markdown and code cells that show instructions to resumt task & jupyter task code.

    Args:
        task_function (function): User's task function.
        notebook_dir (str): Local path to write the example notebook to
    """
    nb = nbf.v4.new_notebook()

    first_cell = "### This file is auto-generated by flyteinteractive"
    second_cell = f"""from flytekit import task
from flytekitplugins.flyteinteractive import jupyter"""
    third_cell = inspect.getsource(task_function)
    fourth_cell = f"{task_function.__name__}()"
    fifth_cell = "### Resume task by shutting down Jupyter: File -> Shut Down"

    nb["cells"] = [
        nbf.v4.new_markdown_cell(first_cell),
        nbf.v4.new_code_cell(second_cell),
        nbf.v4.new_code_cell(third_cell),
        nbf.v4.new_code_cell(fourth_cell),
        nbf.v4.new_markdown_cell(fifth_cell),
    ]
    nbf.write(nb, f"{notebook_dir}/{EXAMPLE_JUPYTER_NOTEBOOK_NAME}")


def exit_handler(
    child_process: multiprocessing.Process,
    task_function,
    args,
    kwargs,
    post_execute: Optional[Callable] = None,
):
    """
    1. Wait for the child process to finish. This happens when the user clicks "Shut Down" in Jupyter
    2. Execute post function, if given.
    3. Executes the task function, when the Jupyter Notebook Server is terminated.

    Args:
        child_process (multiprocessing.Process, optional): The process to be terminated.
        post_execute (function, optional): The function to be executed before the jupyter notebook server is terminated.
    """
    child_process.join()

    if post_execute is not None:
        post_execute()
        logger.info("Post execute function executed successfully!")

    # Get the actual function from the task.
    while hasattr(task_function, "__wrapped__"):
        if isinstance(task_function, jupyter):
            task_function = task_function.__wrapped__
            break
        task_function = task_function.__wrapped__
    return task_function(*args, **kwargs)


JUPYTER_TYPE_VALUE = "jupyter"


class jupyter(ClassDecorator):
    def __init__(
        self,
        task_function: Optional[Callable] = None,
        max_idle_seconds: Optional[int] = MAX_IDLE_SECONDS,
        port: int = 8888,
        enable: bool = True,
        run_task_first: bool = False,
        notebook_dir: Optional[str] = "/root",
        pre_execute: Optional[Callable] = None,
        post_execute: Optional[Callable] = None,
    ):
        """
        jupyter decorator modifies a container to run a Jupyter Notebook server:
        1. Launches and monitors the Jupyter Notebook server.
        2. Write Example Jupyter Notebook.
        3. Terminates if the server is idle for a set duration or user shuts down manually.

        Args:
            task_function (function, optional): The user function to be decorated. Defaults to None.
            max_idle_seconds (int, optional): The duration in seconds to live after no activity detected.
            port (int, optional): The port to be used by the Jupyter Notebook server. Defaults to 8888.
            enable (bool, optional): Whether to enable the Jupyter decorator. Defaults to True.
            run_task_first (bool, optional): Executes the user's task first when True. Launches the Jupyter Notebook server only if the user's task fails. Defaults to False.
            pre_execute (function, optional): The function to be executed before the jupyter setup function.
            post_execute (function, optional): The function to be executed before the jupyter is self-terminated.
        """
        self.max_idle_seconds = max_idle_seconds
        self.port = port
        self.enable = enable
        self.run_task_first = run_task_first
        self.notebook_dir = notebook_dir
        self._pre_execute = pre_execute
        self._post_execute = post_execute

        # arguments are required to be passed in order to access from _wrap_call
        super().__init__(
            task_function,
            max_idle_seconds=max_idle_seconds,
            port=port,
            enable=enable,
            run_task_first=run_task_first,
            notebook_dir=notebook_dir,
            pre_execute=pre_execute,
            post_execute=post_execute,
        )

    def execute(self, *args, **kwargs):
        ctx = FlyteContextManager.current_context()
        logger = flytekit.current_context().logging

        # 1. If the decorator is disabled, we don't launch the Jupyter Notebook server.
        # 2. When user use pyflyte run or python to execute the task, we don't launch the Jupyter Notebook.
        #    Only when user use pyflyte run --remote to submit the task to cluster, we launch the Jupyter Notebook.
        if not self.enable or ctx.execution_state.is_local_execution():
            return self.task_function(*args, **kwargs)

        if self.run_task_first:
            logger.info("Run user's task first")
            try:
                return self.task_function(*args, **kwargs)
            except Exception as e:
                logger.error(f"Task Error: {e}")
                logger.info("Launching Jupyter Notebook Server")

        # 0. Executes the pre_execute function if provided.
        if self._pre_execute is not None:
            self._pre_execute()
            logger.info("Pre execute function executed successfully!")

        # 1. Launches and monitors the Jupyter Notebook server.
        # The following line starts a Jupyter Notebook server with specific configurations:
        #   - '--port': Specifies the port number on which the server will listen for connections.
        #   - '--notebook-dir': Sets the directory where Jupyter Notebook will look for notebooks.
        #   - '--NotebookApp.token='': Disables token-based authentication by setting an empty token.
        logger.info("Start the jupyter notebook server...")
        cmd = f"jupyter notebook --port {self.port} --notebook-dir={self.notebook_dir} --NotebookApp.token=''"

        #   - '--NotebookApp.shutdown_no_activity_timeout': Sets the maximum duration of inactivity
        #     before shutting down the Jupyter Notebook server automatically.
        # When shutdown_no_activity_timeout is 0, it means there is no idle timeout and it is always running.
        if self.max_idle_seconds:
            cmd += (
                f" --NotebookApp.shutdown_no_activity_timeout={self.max_idle_seconds}"
            )
        child_process = multiprocessing.Process(
            target=execute_command,
            kwargs={"cmd": cmd},
        )
        child_process.start()

        write_example_notebook(
            task_function=self.task_function, notebook_dir=self.notebook_dir
        )

        return exit_handler(
            child_process=child_process,
            task_function=self.task_function,
            args=args,
            kwargs=kwargs,
            post_execute=self._post_execute,
        )

    def get_extra_config(self):
        return {self.LINK_TYPE_KEY: JUPYTER_TYPE_VALUE, self.PORT_KEY: str(self.port)}
