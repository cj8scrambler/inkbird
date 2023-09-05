import bluepy
import time
import os

from inkbird.client import InkBirdClient
from inkbird.client import Timer
from inkbird.mqtt import client as mqtt

import logging

logger = logging.getLogger("inkbird")
#logger.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-15s %(levelname)-8s %(message)s"
)


MAX_BACKOFF = 4
INITIAL_BACKOFF = 1

address = os.environ.get("INKBIRD_ADDRESS")
client = InkBirdClient(address)

def upload_latest():
    logger.debug(f"Begin upload loop")
    for p,t in enumerate(client.get_last_probes()):
        logger.debug("  on probe {}: {}".format(p,t))
        if t >= 0 and t < 10000:
            if client.is_deg_f():
                mqtt.publish(f"temp{p+1}", t / 10 * 9 / 5 + 32)
                logger.debug("    Published {} F".format( t / 10 * 9 / 5 + 32))
            else:
                mqtt.publish(f"temp{p+1}", t / 10)
                logger.debug("    Published {} C".format( t / 10))

    b = client.get_last_battery()
    if b:
        mqtt.publish(f"battery", b)

if __name__ == "__main__":

    backoff = 0

    upload_timer = Timer(int(os.environ.get("INKBIRD_MQTT_PERIOD")), upload_latest)
    upload_timer.start()

    mqtt.subscribe("restart")
    mqtt.publish(f"connect", 0)

    while True:
        logger.info(f"Connecting to {address}")
        try:
            client.connect()
            logger.info(f"  Connected to {address}")
            mqtt.publish(f"connect", 1)
            client.login()
            client.enable_data()
            client.enable_battery()

            logger.debug("Starting Loop")
            backoff = INITIAL_BACKOFF
            while True:
                try:
                    if client.client.waitForNotifications(1.0):
                        continue
                except bluepy.btle.BTLEInternalError:
                    pass
        except bluepy.btle.BTLEDisconnectError:
            wait = min(backoff, MAX_BACKOFF)
            mqtt.publish(f"connect", 0)
            logger.info("Unable to connect; Wait {}".format(wait))
            while ('restart' not in mqtt.userdata) and (wait > 0):
                time.sleep(1)
                wait -= 1

            if 'restart' in mqtt.userdata:
                backoff = mqtt.userdata['restart']
                del(mqtt.userdata['restart'])
            else:
                backoff *= 1.5

            if backoff <= 0:
                backoff = 1
