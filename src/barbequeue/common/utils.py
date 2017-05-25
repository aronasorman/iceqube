import abc
import importlib
import logging
import threading
import time

from barbequeue import humanhash


def stringify_func(func):
    assert callable(func), "function {} passed to stringify_func isn't a function!".format(func)

    fqn = "{module}.{funcname}".format(module=func.__module__, funcname=func.__name__)
    return fqn


def import_stringified_func(funcstring):
    assert isinstance(funcstring, str)

    modulestring, funcname = funcstring.rsplit('.', 1)

    mod = importlib.import_module(modulestring)

    func = getattr(mod, funcname)
    return func


class BaseCloseableThread(threading.Thread):
    """
    A base class for a thread that monitors an Event as a signal for shutting down, and a main_loop that otherwise loop
     until the shutdown event is received.
    """
    __metaclass__ = abc.ABCMeta

    DEFAULT_TIMEOUT_SECONDS = 0.2

    def __init__(self, shutdown_event, thread_name, *args, **kwargs):
        assert isinstance(shutdown_event, threading.Event)

        self.shutdown_event = shutdown_event
        self.thread_name = thread_name
        self.thread_id = self._generate_thread_id()
        self.logger = logging.getLogger("{module}.{name}[{id}]".format(module=__name__,
                                                                       name=self.thread_name,
                                                                       id=self.thread_id))
        self.full_thread_name = "{thread_name}-{thread_id}".format(thread_name=self.thread_name,
                                                                   thread_id=self.thread_id)
        super(BaseCloseableThread, self).__init__(name=self.full_thread_name, *args, **kwargs)

    def run(self):
        self.logger.info("Started new {name} thread ID#{id}".format(name=self.thread_name,
                                                                    id=self.thread_id))

        while True:
            if self.shutdown_event.wait(self.DEFAULT_TIMEOUT_SECONDS):
                self.logger.warning("{name} shut down event received; closing.".format(name=self.thread_name))
                self.shutdown()
                break
            else:
                self.main_loop(timeout=self.DEFAULT_TIMEOUT_SECONDS)
                continue

    @abc.abstractmethod
    def main_loop(self, timeout):
        """
        The main loop of a thread. Run this loop if we haven't received any shutdown events in the last 
        timeout seconds. Normally this is used to read from a queue; you are encouraged to return from 
        this function if the timeout parameter has elapsed, to allow the thread to continue to check
        for the shutdown event.
        :param timeout: a parameter determining how long you can wait for a timeout.
        :return: None
        """
        pass

    @staticmethod
    def _generate_thread_id():
        uid, _ = humanhash.uuid()
        return uid

    def shutdown(self):
        # stub method, override if you need a more complex shut down procedure.
        pass


class InfiniteLoopThread(BaseCloseableThread):
    """A class that runs a given function an infinite number of times, until told to shut down."""

    def __init__(self, func, thread_name, wait_between_runs=1):
        """
        Run the given func continuously until either shutdown_event is set, or the python interpreter exits.
        :param func: the function to run. This should accept no arguments.
        :param thread_name: the name of the thread to use during logging and debugging
        :param wait_between_runs: how many seconds to wait in between func calls.
        """
        self.shutdown_event = threading.Event()
        super(InfiniteLoopThread, self).__init__(thread_name=thread_name, shutdown_event=self.shutdown_event)
        self.func = func
        self.wait = wait_between_runs
        self.daemon = True

    def main_loop(self, timeout):
        try:
            self.func()
        except Exception as e:
            self.logger.warning("Got an exception running {func}: {e}".format(func=self.func, e=str(e)))

        time.sleep(self.wait)

    def cancel(self):
        self.shutdown_event.set()