import os
import array
import struct
import logging
import threading

from bluepy import btle

from . import const
from collections import defaultdict

logger = logging.getLogger("inkbird-client")
logger.setLevel(logging.WARN)

class Timer(threading.Timer):
    def run(self):
        while not self.finished.is_set():
            self.finished.wait(self.interval)
            self.function(*self.args, **self.kwargs)
        self.finished.set()

class Delegate(btle.DefaultDelegate):
    def __init__(self, address):
        super().__init__()
        self.address = address
        self.probes_update = False
        self.probes = []
        self.battery_update = False
        self.battery = None

    def handleNotification(self, cHandle, data):
        logger.debug("Received notification: {}".format(cHandle))
        if cHandle == 48:
            self.handleTemperature(data)
        if cHandle == 37:
            self.handleBattery(data)

    def handleTemperature(self, data):
        temp = array.array("H")
        temp.fromstring(data)
        if len(temp) > len(self.probes):
            self.probes = [None] * len(temp)
        for p, t in enumerate(temp):
            self.probes[p] = t
        self.probes_update = True
        logger.info("Temp updates: {}".format(self.probes))

    def __batteryPercentage(self, current, max):
        factor = max / 6550.0
        current /= factor
        if current > const.BATTERY_CORRECTION[-1]:
            return 100
        if current <= const.BATTERY_CORRECTION[0]:
            return 0
        for idx, voltage in enumerate(const.BATTERY_CORRECTION, start=0):
            if (current > voltage) and (current <= (const.BATTERY_CORRECTION[idx + 1])):
                return idx + 1
        return 100

    def handleBattery(self, data):
        if data[0] != 36:
            return
        battery, maxBattery = struct.unpack("<HH", data[1:5])
        self.battery = self.__batteryPercentage(battery, maxBattery)
        self.battery_update = True
        logger.info("Battery update: {}".format(self.battery))

class InkBirdClient:
    def __init__(self, address):
        self.address = address
        self.units = os.environ.get("INKBIRD_TEMP_UNITS", "f").lower()
        self.delegate = None

    def connect(self):
        self.client = btle.Peripheral(self.address)
        self.service = self.client.getServiceByUUID("FFF0")
        self.characteristics = self.service.getCharacteristics()
        self.delegate = Delegate(self.address)
        self.client.setDelegate(self.delegate)
        self.client.writeCharacteristic(
            self.characteristics[0].getHandle() + 1, b"\x01\x00", withResponse=True
        )
        self.client.writeCharacteristic(
            self.characteristics[3].getHandle() + 1, b"\x01\x00", withResponse=True
        )
        logger.info("Connect success")

    def login(self):
        self.characteristics[1].write(const.CREDENTIALS_MESSAGE, withResponse=True)

    def enable_data(self):
        if self.units == "c":
            self.set_deg_c()
        else:
            self.set_deg_f()
        self.characteristics[4].write(
            const.REALTIME_DATA_ENABLE_MESSAGE, withResponse=True
        )

    def enable_battery(self):
        self.request_battery()
        timer = Timer(300.0, self.request_battery)
        timer.start()

    def request_battery(self):
        logger.debug("Requesting battery")
        try:
            self.characteristics[4].write(const.REQ_BATTERY_MESSAGE, withResponse=True)
        except (btle.BTLEInternalError, btle.BTLEDisconnectError):
            pass

    def set_deg_f(self):
        self.characteristics[4].write(const.UNITS_F_MESSAGE, withResponse=True)

    def set_deg_c(self):
        self.characteristics[4].write(const.UNITS_C_MESSAGE, withResponse=True)

    def is_deg_f(self):
        if self.units == "f":
            return True
        return False

    def read_temperature(self):
        return self.service.peripheral.readCharacteristic(
            self.characteristics[3].handle
        )

    def get_last_probes(self):
        if self.delegate:
            logger.debug("  get_last_probes() have delegate")
        if self.delegate and self.delegate.probes_update:
            logger.debug("  get_last_probes() have probes_update")
            self.delegate.probes_update = False
            return self.delegate.probes
        return []

    def get_last_battery(self):
        if self.delegate and self.delegate.battery_update:
            self.delegate.battery_update = False
            return self.delegate.battery
        return None
