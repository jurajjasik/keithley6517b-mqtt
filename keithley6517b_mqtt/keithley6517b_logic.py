import logging
import threading
from threading import Event
import time
from concurrent.futures import Future
from ctypes import Array
from functools import wraps
from queue import Queue

from pymeasure.instruments import Instrument
from pymeasure.instruments.keithley import Keithley6517B
from pyvisa import VisaIOError

logger = logging.getLogger(__name__)


class MyKeithley6517B(Keithley6517B):

    current = Instrument.measurement(
        ":READ?",
        """ Reads the current in Amps, if configured for this reading.
        """,
        get_process=Keithley6517B.extract_value,
    )

    def __call__(self, *args, **kwds):
        return super().__call__(*args, **kwds)


class KeithleyDeviceIOError(Exception):
    """Exception raised when the Keithley peripheral IO error."""

    pass


def check_connection_decorator(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        self.check_connection()
        try:
            return method(self, *args, **kwargs)
        except VisaIOError as e:
            self._is_connected.clear()
            raise KeithleyDeviceIOError(f"Keithley peripheral IO error: {e}")

    return wrapper


# decorator that pushes the method to the queue and returns the future result
def push_method_to_queue_decorator(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        future = Future()
        self.queue.put((method, self, args, kwargs, future))
        time.sleep(self.config["current_measurement_interval"])
        try:
            return future.result(timeout=10)
        except TimeoutError:
            logger.error(f"Timeout error in method {method.__name__}")
            return None

    return wrapper


class WorkerThread(threading.Thread):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            try:
                method, that, args, kwargs, future = self.queue.get(timeout=1)
                future.set_result(method(that, *args, **kwargs))
            except TimeoutError:
                pass
            except Exception as e:
                logger.error(f"Error in worker thread: {e}")

    def stop(self):
        self._stop_event.set()


class Keithley6517BLogic:
    def __init__(self, config, on_connected):
        self.config = config
        self.on_connected = on_connected

        self._is_connected = Event()

        self.device = None

        self.queue = Queue()
        self.worker_thread = WorkerThread(self.queue)

    def start_worker_thread(self):
        self.worker_thread.start()

    def stop_worker_thread(self):
        self.worker_thread.stop()
        self.worker_thread.join()

    def check_connection(self):
        if not self.is_connected():
            self.try_connect()

    def try_connect(self):
        try:
            logger.info(
                f"Connecting to Keithley 6517B at {self.config['keithley_visa_resource']} ..."
            )
            self.device = MyKeithley6517B(
                self.config["keithley_visa_resource"],
                asrl={"baud_rate": self.config["keithley_baud_rate"]},
                timeout=self.config["keithley_timeout"],
            )

            self._is_connected.set()
            logger.info("Keithley 6517B connected.")
            if self.on_connected is not None:
                self.on_connected()

        except VisaIOError as e:
            self._is_connected.clear()
            raise KeithleyDeviceIOError(f"Keithley peripheral connection error: {e}")

    def is_connected(self):
        return self._is_connected.is_set()

    @push_method_to_queue_decorator
    @check_connection_decorator
    def apply_voltage(self, value):
        self.device.apply_voltage(value)

    @property
    @push_method_to_queue_decorator
    @check_connection_decorator
    def current(self) -> float:
        logger.debug("Reading current from Keithley 6517B ...")
        return self.device.current

    @current.setter
    @push_method_to_queue_decorator
    @check_connection_decorator
    def current(self, value):
        self.device.current = value

    @property
    @push_method_to_queue_decorator
    @check_connection_decorator
    def current_nplc(self) -> float:
        return self.device.current_nplc

    @push_method_to_queue_decorator
    @check_connection_decorator
    def auto_range_source(self):
        self.device.auto_range_source()

    @property
    @push_method_to_queue_decorator
    @check_connection_decorator
    def voltage_range(self) -> float:
        return self.device.voltage_range

    @voltage_range.setter
    @push_method_to_queue_decorator
    @check_connection_decorator
    def voltage_range(self, value):
        self.device.voltage_range = value

    @property
    @push_method_to_queue_decorator
    @check_connection_decorator
    def current_range(self) -> float:
        return self.device.current_range

    @current_range.setter
    @push_method_to_queue_decorator
    @check_connection_decorator
    def current_range(self, value):
        self.device.current_range = value

    @property
    @push_method_to_queue_decorator
    @check_connection_decorator
    def source_enabled(self) -> bool:
        return self.device.source_enabled

    @source_enabled.setter
    @push_method_to_queue_decorator
    @check_connection_decorator
    def source_enabled(self, value):
        self.enable_source() if value else self.disable_source()

    @push_method_to_queue_decorator
    @check_connection_decorator
    def disable_source(self):
        logger.debug("Disabling source ...")
        self.device.disable_source()

    @push_method_to_queue_decorator
    @check_connection_decorator
    def enable_source(self):
        logger.debug("Enabling source ...")
        self.device.enable_source()

    @push_method_to_queue_decorator
    @check_connection_decorator
    def measure_current(self, nplc, current, auto_range):
        return self.device.measure_current(nplc, current, auto_range)

    @push_method_to_queue_decorator
    @check_connection_decorator
    def reset(self):
        self.device.reset()

    @push_method_to_queue_decorator
    @check_connection_decorator
    def shutdown(self):
        self.device.shutdown()

    @property
    @push_method_to_queue_decorator
    @check_connection_decorator
    def source_voltage(self) -> float:
        return self.device.source_voltage

    @source_voltage.setter
    @push_method_to_queue_decorator
    @check_connection_decorator
    def source_voltage(self, value):
        self.device.source_voltage = value

    @property
    @push_method_to_queue_decorator
    @check_connection_decorator
    def source_voltage_range(self) -> float:
        return self.device.source_voltage_range

    @source_voltage_range.setter
    @push_method_to_queue_decorator
    @check_connection_decorator
    def source_voltage_range(self, value):
        self.device.source_voltage_range = value
