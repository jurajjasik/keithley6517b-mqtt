import json
import logging
import socket
from functools import wraps
from select import select
from threading import Event, Thread
from time import time

import paho.mqtt.client as mqtt
import yaml

from .keithley6517b_logic import Keithley6517BLogic, KeithleyDeviceIOError

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def all_in(keys, dictionary):
    return all(key in dictionary for key in keys)


def handle_connection_error(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        logger.debug(
            f"Calling method: {method.__name__} with args: {args} and kwargs: {kwargs}"
        )
        try:
            result = method(self, *args, **kwargs)
            logger.debug(f"Method {method.__name__} returned: {result}")
            return result
        except KeithleyDeviceIOError as e:
            command = method.__name__.split("_")[1]  # Extract command from method name
            logger.warning(f"Error in method {method.__name__}: {e}")
            self.publish_connection_error(command, str(e))

    return wrapper


class Keithley6517BMQTTClientNotConnectedException(Exception):
    """Exception raised when the Keithley6517BMQTTClient could not connect to the broker."""

    def __init__(
        self,
        additional_massage="",
        message="Keithley6517BMQTTClient could not connect to the broker.",
    ):
        super().__init__(message + " " + additional_massage)


class Keithley6517BMQTTClient:
    def __init__(self, config_file):
        self.config = self.load_config(config_file)
        self.topic_base = self.config["topic_base"]
        self.device_name = self.config["device_name"]

        self.user_stop_event = Event()
        self.measure_continously = Event()

        self.keithley = Keithley6517BLogic(
            self.config, on_connected=self.keithley_connected
        )

    def main(self):
        self.disconnected = (False, None)

        self.client = mqtt.Client(
            client_id=self.config["client_id"],
            clean_session=False,
        )
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        self.connect_to_broker()

        self.keithley.start_worker_thread()

        self.last_time = time()
        self.client.loop_start()

        while not self.disconnected[0] and not self.user_stop_event.is_set():
            # self.do_select()
            if time() - self.last_time > self.config["current_measurement_interval"]:
                self.last_time = time()
                self.perform_current_measurement()

        self.client.loop_stop()
        self.client = None

    def load_config(self, config_file):
        with open(config_file, "r") as file:
            config = yaml.safe_load(file)
        return config

    def connect_to_broker(self):
        logger.debug(
            f'Connecting client_id {self.config["client_id"]} to brooker {self.config["mqtt_broker"]}:{self.config["mqtt_port"]}...'
        )
        try:
            self.client.connect(
                self.config["mqtt_broker"],
                self.config["mqtt_port"],
                self.config["mqtt_connection_timeout"],
            )
            self.client.socket().setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2048)
        except Exception as e:
            logger.warning(f"Could not connect to broker. Error: {e}")
            self.disconnected = True, -1

    def on_connect(self, client, userdata, flags, reason_code):
        logger.debug(f"on_connect with reason code {reason_code}")
        if reason_code != 0:
            self.disconnected = True, reason_code
            raise Keithley6517BMQTTClientNotConnectedException(
                f"reason_code = {reason_code}"
            )

        # Subscribe to command topics
        self.client.subscribe(f"{self.topic_base}/cmnd/{self.device_name}/#")

    def on_disconnect(self, client, userdata, flags, reason_code):
        logger.debug(f"on_disconnect with reason code {reason_code}")
        self.disconnected = True, reason_code

    def on_message(self, client, userdata, message):
        topic = message.topic

        try:
            payload = json.loads(message.payload.decode())
        except json.JSONDecodeError as e:
            logger.debug(f"Error decoding message payload: {e}")
            payload = {}

        logger.debug(f"Received message on topic {topic} with payload {payload}")

        if topic.endswith("/apply_voltage"):
            self.handle_apply_voltage(payload)
        elif topic.endswith("/auto_range_source"):
            self.handle_auto_range_source(payload)
        elif topic.endswith("/current"):
            self.handle_current(payload)
        elif topic.endswith("/current_range"):
            self.handle_current_range(payload)
        elif topic.endswith("/disable_source"):
            self.handle_disable_source(payload)
        elif topic.endswith("/enable_source"):
            self.handle_enable_source(payload)
        elif topic.endswith("/measure_continously"):
            self.handle_measure_continously(payload)
        elif topic.endswith("/measure_current"):
            self.handle_measure_current(payload)
        elif topic.endswith("/reset"):
            self.handle_reset(payload)
        elif topic.endswith("/shutdown"):
            self.handle_shutdown(payload)
        elif topic.endswith("/source_enabled"):
            self.handle_source_enabled(payload)
        elif topic.endswith("/source_voltage"):
            self.handle_source_voltage(payload)
        elif topic.endswith("/source_voltage_range"):
            self.handle_source_voltage_range(payload)
        else:
            logger.warning(f"Unknown topic {topic}")

    @handle_connection_error
    def handle_apply_voltage(self, payload):
        voltage = "None"
        if "value" in payload:
            voltage = payload["value"]
        if voltage == "None" or is_number(voltage):
            measure_continously_value = self.measure_continously.is_set()
            self.measure_continously.clear()
            logger.debug(f"Applying voltage {voltage} to the device")
            self.keithley.apply_voltage(voltage)
            self.publish_response("apply_voltage", voltage, payload)
            (
                self.measure_continously.set()
                if measure_continously_value
                else self.measure_continously.clear()
            )
            self.publish_measure_continously(payload, self.measure_continously.is_set())
        else:
            self.publish_error("apply_voltage", f"Invalid voltage range: {voltage}")

    @handle_connection_error
    def handle_auto_range_source(self, payload):
        measure_continously_value = self.measure_continously.is_set()
        self.measure_continously.clear()
        logger.debug(f"Setting auto_range_source.")
        self.keithley.auto_range_source()
        rng = self.keithley.voltage_range
        self.publish_response("voltage_range", rng, payload)
        (
            self.measure_continously.set()
            if measure_continously_value
            else self.measure_continously.clear()
        )
        self.publish_measure_continously(payload, self.measure_continously.is_set())

    @handle_connection_error
    def handle_current(self, payload):
        measure_continously_value = self.measure_continously.is_set()
        self.measure_continously.clear()
        logger.debug("Getting current")
        current = self.keithley.current
        self.publish_response("current", current, payload)
        (
            self.measure_continously.set()
            if measure_continously_value
            else self.measure_continously.clear()
        )
        self.publish_measure_continously(payload, self.measure_continously.is_set())

    @handle_connection_error
    def handle_current_range(self, payload):
        measure_continously_value = self.measure_continously.is_set()
        self.measure_continously.clear()
        if "value" in payload:
            current_range = payload["value"]
            logger.debug(f"Setting current range to {current_range}")
            self.keithley.current_range = current_range
        logger.debug("Getting current range")
        current_range = self.keithley.current_range
        self.publish_response("current_range", current_range, payload)
        (
            self.measure_continously.set()
            if measure_continously_value
            else self.measure_continously.clear()
        )
        self.publish_measure_continously(payload, self.measure_continously.is_set())

    @handle_connection_error
    def handle_disable_source(self, payload):
        measure_continously_value = self.measure_continously.is_set()
        self.measure_continously.clear()
        logger.debug("Disabling source")
        self.keithley.disable_source()
        enabled = self.keithley.source_enabled
        self.publish_response("source_enabled", enabled, payload)
        (
            self.measure_continously.set()
            if measure_continously_value
            else self.measure_continously.clear()
        )
        self.publish_measure_continously(payload, self.measure_continously.is_set())

    @handle_connection_error
    def handle_enable_source(self, payload):
        measure_continously_value = self.measure_continously.is_set()
        self.measure_continously.clear()
        logger.debug("Enabling source")
        self.keithley.enable_source()
        enabled = self.keithley.source_enabled
        self.publish_response("source_enabled", enabled, payload)
        (
            self.measure_continously.set()
            if measure_continously_value
            else self.measure_continously.clear()
        )
        self.publish_measure_continously(payload, self.measure_continously.is_set())

    @handle_connection_error
    def handle_measure_current(self, payload):
        measure_continously_value = self.measure_continously.is_set()
        self.measure_continously.clear()
        if all_in(["nplc", "current", "auto_range"], payload):
            nplc = payload["nplc"]
            current = payload["current"]
            auto_range = payload["auto_range"]
            logger.debug(
                f"Configures the Keithley 6517B to measure current with nplc={nplc}, current={current}, auto_range={auto_range}"
            )
            self.keithley.measure_current(nplc, current, auto_range)
        rng = self.keithley.current_range
        self.publish_response("current_range", rng, payload)
        (
            self.measure_continously.set()
            if measure_continously_value
            else self.measure_continously.clear()
        )
        self.publish_measure_continously(payload, self.measure_continously.is_set())

    @handle_connection_error
    def handle_reset(self, payload):
        self.measure_continously.clear()
        logger.debug("Resetting the device")
        self.keithley.reset()
        self.publish_response("reset", "done", payload)
        self.publish_measure_continously(False, payload)

    @handle_connection_error
    def handle_shutdown(self, payload):
        self.measure_continously.clear()
        logger.debug("Shutting down the device")
        self.keithley.shutdown()
        source_enabled = self.keithley.source_enabled
        self.publish_response("source_enabled", source_enabled, payload)
        self.publish_measure_continously(False, payload)

    @handle_connection_error
    def handle_measure_continously(self, payload):
        if "value" in payload:
            measure_continously = bool(payload["value"])
            logger.debug(f"Setting measure_continously to {measure_continously}")
            (
                self.measure_continously.set()
                if measure_continously
                else self.measure_continously.clear()
            )
        logger.debug("Getting measure_continously")
        measure_continously = self.measure_continously.is_set()
        self.publish_measure_continously(payload, measure_continously)

    def publish_measure_continously(self, payload, measure_continously):
        self.publish_response("measure_continously", measure_continously, payload)

    @handle_connection_error
    def handle_source_enabled(self, payload):
        measure_continously_value = self.measure_continously.is_set()
        self.measure_continously.clear()
        if "value" in payload:
            source_enabled = payload["value"]
            logger.debug(f"Setting source_enabled to {source_enabled}")
            self.keithley.source_enabled = source_enabled
        logger.debug("Getting source_enabled")
        source_enabled = self.keithley.source_enabled
        self.publish_response("source_enabled", source_enabled, payload)
        (
            self.measure_continously.set()
            if measure_continously_value
            else self.measure_continously.clear()
        )
        self.publish_measure_continously(payload, self.measure_continously.is_set())

    @handle_connection_error
    def handle_source_voltage(self, payload):
        measure_continously_value = self.measure_continously.is_set()
        self.measure_continously.clear()
        if "value" in payload:
            voltage = payload["value"]
            logger.debug(f"Setting source_voltage to {voltage}")
            self.keithley.source_voltage = voltage
        logger.debug("Getting source_voltage")
        voltage = self.keithley.source_voltage
        self.publish_response("source_voltage", voltage, payload)
        (
            self.measure_continously.set()
            if measure_continously_value
            else self.measure_continously.clear()
        )
        self.publish_measure_continously(payload, self.measure_continously.is_set())

    @handle_connection_error
    def handle_source_voltage_range(self, payload):
        measure_continously_value = self.measure_continously.is_set()
        self.measure_continously.clear()
        if "value" in payload:
            source_voltage_range = payload["value"]
            logger.debug(f"Setting source_voltage_range to {source_voltage_range}")
            self.keithley.source_voltage_range = source_voltage_range
        logger.debug("Getting source_voltage_range")
        source_voltage_range = self.keithley.source_voltage_range
        self.publish_response("source_voltage_range", source_voltage_range, payload)
        (
            self.measure_continously.set()
            if measure_continously_value
            else self.measure_continously.clear()
        )
        self.publish_measure_continously(payload, self.measure_continously.is_set())

    def publish_error(self, command, error_message):
        if self.client is not None and self.client.is_connected():
            topic = f"{self.topic_base}/error/{self.device_name}/command"
            payload = json.dumps({"command": command, "error_message": error_message})
            self.client.publish(topic, payload)

    def publish_connection_error(self, command, error_message):
        if self.client is not None and self.client.is_connected():
            error_payload = json.dumps({"error": error_message, "command": command})
            self.client.publish(
                f"{self.topic_base}/error/{self.device_name}/disconnected",
                json.dumps(error_payload),
            )
            logger.debug(f"Publish connection error: {error_message}")

    def publish_response(self, command, value, sender_payload):
        if self.client is not None and self.client.is_connected():
            response_payload = json.dumps(
                {"value": value, "sender_payload": sender_payload}
            )
            topic = f"{self.topic_base}/response/{self.device_name}/{command}"
            self.client.publish(
                topic,
                response_payload,
            )
            logger.debug(f"Publish topic: {topic}, payload: {response_payload}")

    def keithley_connected(self):
        if self.client is not None and self.client.is_connected():
            topic = f"{self.topic_base}/connected/{self.device_name}"
            payload = "1"
            self.client.publish(topic, payload, retain=True)
            logger.debug(f"Published keithley connected status to {topic}")

            # self.client.publish(
            #     f"{self.topic_base}/response/{self.device_name}/measure_continously",
            #     json.dumps({"value": self.measure_continously}),
            # )

            # self.client.publish(
            #     f"{self.topic_base}/response/{self.device_name}/source_enabled",
            #     json.dumps({"value": self.keithley.source_enabled}),
            # )

            # self.client.publish(
            #     f"{self.topic_base}/response/{self.device_name}/source_voltage",
            #     json.dumps({"value": self.keithley.source_voltage}),
            # )

            # self.client.publish(
            #     f"{self.topic_base}/response/{self.device_name}/source_voltage_range",
            #     json.dumps({"value": self.keithley.source_voltage_range}),
            # )

            # self.client.publish(
            #     f"{self.topic_base}/response/{self.device_name}/current_range",
            #     json.dumps({"value": self.keithley.current_range}),
            # )

            # self.client.publish(
            #     f"{self.topic_base}/response/{self.device_name}/nplc",
            #     json.dumps({"value": self.keithley.current_nplc}),
            # )

    def stop(self):
        logger.debug("User stop")
        self.user_stop_event.set()
        self.measure_continously.clear()
        self.keithley.stop_worker_thread()

    def perform_current_measurement(self):
        logger.debug("Time to measure current")
        if self.client.is_connected() and self.measure_continously.is_set():
            self.handle_current(payload=json.dumps({"regular": True}))
