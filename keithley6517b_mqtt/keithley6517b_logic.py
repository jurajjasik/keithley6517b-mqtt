import logging
from ctypes import Array
from functools import wraps

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
            self._is_connected = False
            raise KeithleyDeviceIOError(f"Keithley peripheral IO error: {e}")

    return wrapper


class Keithley6517BLogic:
    def __init__(self, config, on_connected):
        self.config = config
        self.on_connected = on_connected

        self._is_connected = False

        self.device = None

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
            )

            self._is_connected = True
            logger.info("Keithley 6517B connected.")
            if self.on_connected is not None:
                self.on_connected()

        except VisaIOError as e:
            self._is_connected = False
            raise KeithleyDeviceIOError(f"Keithley peripheral connection error: {e}")

    def is_connected(self):
        return self._is_connected

    @check_connection_decorator
    def apply_voltage(self, value):
        self.device.apply_voltage(value)

    @property
    @check_connection_decorator
    def current(self) -> float:
        return self.device.current

    @current.setter
    @check_connection_decorator
    def current(self, value):
        self.device.current = value

    @check_connection_decorator
    def auto_range_source(self):
        self.device.auto_range_source()

    @property
    @check_connection_decorator
    def voltage_range(self) -> float:
        return self.device.voltage_range

    @voltage_range.setter
    @check_connection_decorator
    def voltage_range(self, value):
        self.device.voltage_range = value

    @property
    @check_connection_decorator
    def current_range(self) -> float:
        return self.device.current_range

    @current_range.setter
    @check_connection_decorator
    def current_range(self, value):
        self.device.current_range = value

    @property
    @check_connection_decorator
    def source_enabled(self) -> bool:
        return self.device.source_enabled

    @source_enabled.setter
    @check_connection_decorator
    def source_enabled(self, value):
        self.enable_source() if value else self.disable_source()

    @check_connection_decorator
    def disable_source(self):
        self.device.disable_source()

    @check_connection_decorator
    def enable_source(self):
        self.device.enable_source()

    @check_connection_decorator
    def measure_current(self, nplc, current, auto_range):
        return self.device.measure_current(nplc, current, auto_range)

    @check_connection_decorator
    def reset(self):
        self.device.reset()

    @check_connection_decorator
    def shutdown(self):
        self.device.shutdown()

    @property
    @check_connection_decorator
    def source_enabled(self) -> bool:
        return self.device.source_enabled

    @source_enabled.setter
    @check_connection_decorator
    def source_enabled(self, value):
        self.device.source_enabled = value

    @property
    @check_connection_decorator
    def source_voltage(self) -> float:
        return self.device.source_voltage

    @source_voltage.setter
    @check_connection_decorator
    def source_voltage(self, value):
        self.device.source_voltage = value

    @property
    @check_connection_decorator
    def source_voltage_range(self) -> float:
        return self.device.source_voltage_range

    @source_voltage_range.setter
    @check_connection_decorator
    def source_voltage_range(self, value):
        self.device.source_voltage_range = value
