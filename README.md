# Keithley6517B-MQTT

## Overview
This MQTT client facilitates communication with the Keithley6517B electromer using MQTT.
The client leverages the Pymeasure https://pymeasure.readthedocs.io/en/latest/api/instruments/keithley/keithley6517b.html library for direct interaction with the Keithley6517B electromer.

## Dependencies
- Pymeasure

## Configuration
The MQTT client requires a configuration file where you can specify various settings, including the base topic and device name.

### Configuration Options
- topic_base: The base topic used for all MQTT messages. This should be defined in the configuration file.
- device_name: The name of the Keithley6517B device. Default is Keithley6517B, but this can be customized, especially useful when managing multiple devices.

## MQTT Message Structure
The client communicates using MQTT messages structured as `<topic_base>/<action>/<device_name>/<command>`.

### Status Messages

These messages are sent by the client to provide information about the connection status of the QSource3 device.

#### `<topic_base>/connected/<device_name>` 

- **Description**: This topic identifies the connected Keithley6517B device. Subscribing to this topic allows you to check if the device is connected.
- **Message**: A retained message (QOS = 1) is published on this topic when the device is connected.

### Error Messages

These messages are sent by the client when there are issues such as disconnection.

#### `<topic_base>/error/disconnected/<device_name>`

- **Description**: This topic is used to notify when the Keithley6517B device is disconnected.

### Command Messages

These are the commands subscribed by the client to control the internal state of the Keithley6517B device.

- **Structure**: `<topic_base>/cmnd/<device_name>/<command>`
- **Payload**: The payload typically includes a `"value"` field that sets the new value or retrieves the current value.
- **Response**: A corresponding response message or an error message is published based on the outcome of the command.

#### `<topic_base>/cmnd/<device_name>/current`

- **Description**: Reads the current in Amps, if configured for this reading.
- **Payload**: 
  - No payload is required for this command. It acts as a getter to retrieve the current.
- **Response Message**: 
  - `<topic_base>/response/<device_name>/current`
- **Error Message**: 
  - `<topic_base>/error/disconnected/<device_name>`

### Response Messages

These messages are sent by the client in response to command messages. 

#### `<topic_base>/response/<device_name>/current`

- **Description**: Returns the current in Amps, if configured for this reading.
- **Payload**: 
  - `"value": <float>` - The current in Amps.
  - `"sender_payload": [<corresponding command's message payload>]` - The original command's payload for tracking.

> Example Payload:
> ```json
> {
>   "value": 3.2e-10,
>   "sender_payload": {}
> }
> ```
