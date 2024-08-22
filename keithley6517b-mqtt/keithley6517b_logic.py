from ctypes import Array
from functools import wraps

from pymeasure.instruments.keithley import Keithley6517B
from pyvisa import VisaIOError


class KeithleyNotConnectedException(Exception):
    """Exception raised when the QSource3 peripheral is not connected."""

    pass


def check_connection_decorator(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        self.check_connection()
        try:
            return method(self, *args, **kwargs)
        except VisaIOError:
            self.is_connected = False
            raise KeithleyNotConnectedException("QSource3 peripheral is not connected.")

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
            self.device = Keithley6517B(self.config["keithley_visa_resource"])

            self._is_connected = True
            if self.on_connected is not None:
                self.on_connected()

        except VisaIOError:
            self._is_connected = False
            raise KeithleyNotConnectedException("Keithley peripheral is not connected.")

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
