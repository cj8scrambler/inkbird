import paho.mqtt.client as mqtt
import time
import os
import logging

logger = logging.getLogger("inkbird-mqtt")
logger.setLevel(logging.INFO)

def remove_prefix(text, prefix):
    return text[text.startswith(prefix) and len(prefix):]

def on_message(client, userdata, message):
    logger.info("Received message " + str(message.payload) + " on topic '" + message.topic);
    key = remove_prefix(message.topic, userdata['feedpath']+".")
    value = int(message.payload) 
    userdata[key] = value

class MqttController:
    userdata = {}

    def __init__(self, last_will = None):
        self.setup()


    def setup(self):
        host = os.environ.get("INKBIRD_MQTT_HOST")
        port = int(os.environ.get("INKBIRD_MQTT_PORT", 1883))
        username = os.environ.get("INKBIRD_MQTT_USERNAME", "")
        password = os.environ.get("INKBIRD_MQTT_PASSWORD", "")
        self.userdata['feedpath'] = username + "/feeds/inkbird"

        client = mqtt.Client(client_id="inkbird", userdata=self.userdata)
        client.on_message = on_message
        client.will_set(self.userdata['feedpath']+".connect", 0)

        client.username_pw_set(username, password)
        try:
            client.connect(host=host, port=port)
            client.loop_start()
            self.client = client
            logger.info("Connected to {}:{}".format(host, port))
            timeout=50
            while (not client.is_connected()) and timeout:
                timeout -= 1
                time.sleep(0.1)
            if timeout == 0:
                logger.info("Failed to verify connection")
                self.client = None
        except:
            logger.info("Connection to {}:{} failed".format(host, port))
            self.client = None

    def publish(self, topic, message, retainMessage=False):
        if not self.connected():
            self.setup()

        if self.connected():
            self.client.publish(self.userdata['feedpath']+"."+topic, message, retain=retainMessage)
            logger.info("Published '{}' to '{}'".format(message, self.userdata['feedpath']+"."+topic))

    def subscribe(self, topic):
        if not self.connected():
            self.setup()

        if self.connected():
            self.client.subscribe(self.userdata['feedpath']+"."+topic)
            logger.info("Subscribed to '{}'".format(self.userdata['feedpath']+"."+topic))

    def connected(self):
        result = False
        if self.client is not None:
            result = self.client.is_connected()
        return result

client = MqttController()
