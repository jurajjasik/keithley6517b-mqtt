import logging
import time

from keithley6517b_mqtt.keithley6517b_mqtt_client import Keithley6517BMQTTClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    else:
        config_file = "config.yaml"

    client = Keithley6517BMQTTClient(config_file)

    try:
        while True:
            client.main()
            logger.info(
                f"Main loop stopped. Disconnected status: {client.disconnected}"
            )
            logger.info("Attempt to reconnect in 5 seconds ...")
            time.sleep(5)
    except KeyboardInterrupt:
        if client is not None:
            client.stop()
