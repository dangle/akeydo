"""Utility functions for working with asyncio Tasks.

Functions:
    handle_exception: A callback function to be attached to tasks that will log
        any exception other than CancelledError and stops the running loops.
"""

import asyncio
import logging

__all__ = (
    "create_task",
    "handle_exception",
)


def handle_exception(task: asyncio.Task) -> None:
    """Handle any exceptions that occur in tasks.

    Log all errors and stop the event loop when any exception other than
    asyncio.CancelledError is raised.

    Args:
        task: The task that raised the exception.
    """
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        if logging.getLogger().level == logging.DEBUG:
            logging.exception("Exception raised by task %s", task.get_name())
        else:
            logging.error("%s", e)
        context_loop = asyncio.get_event_loop()
        task_loop = task.get_loop()
        if task_loop is not context_loop:
            task_loop.stop()
        context_loop.stop()


def create_task(coro, *, name=None) -> asyncio.Task:
    """Create a task in the current event loop and add an exception handler.

    Args:
        coro: The coroutine to use to create the task.
        name: An optional name for the coroutine.

    Returns: An asyncio.Task configured with a done callback that logs
        exceptions stops the loop.
    """
    task = asyncio.get_event_loop().create_task(coro, name=name)
    task.add_done_callback(handle_exception)
    return task
