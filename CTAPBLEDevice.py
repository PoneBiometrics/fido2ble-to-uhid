#!/usr/bin/env python
import asyncio
import enum
import logging
from functools import partial
from dbus_fast import BusType
from dbus_fast.aio import ProxyInterface, MessageBus

class CTAPBLE_CMD(enum.IntEnum):
    PING = 0x81
    KEEPALIVE = 0x82
    MSG = 0x83
    CANCEL = 0xBE
    ERROR = 0xBF


class CTAPBLE_KEEPALIVE(enum.IntEnum):
    PROCESSING = 0x01
    UP_NEEDED = 0x02


class CTAPBLE_ERROR(enum.IntEnum):
    """ERROR constants and values for BLE.

    See: https://fidoalliance.org/specs/fido-v2.1-rd-20210309/fido-client-to-authenticator-protocol-v2.1-rd-20210309.html#ble-constants
    """

    INVALID_CMD = 0x01
    INVALID_PAR = 0x02
    INVALID_LEN = 0x03
    INVALID_SEQ = 0x04
    REQ_TIMEOUT = 0x05
    BUSY = 0x06
    LOCK_REQUIRED = 0x0A  # only relevant in HID
    INVALID_CHANNEL = 0x0B  # only relevant in HID
    OTHER = 0x7F



def notify_message(handler, interface_name, changed_properties, invalidated_properties):
    # Add check here for message length and read until done then close connection
    # Should bind this with USB as well as just direct translate.
    # Will most likely need read whole message to repackage as USB has different size
    if 'Value' in changed_properties:
        handler(changed_properties['Value'].value)


class CTAPBLEDevice:
    device: ProxyInterface  # org.bluez.Device1
    device_id: str
    connected = False

    fido_control_point: ProxyInterface  # org.bluez.GattCharacteristic1
    fido_status: ProxyInterface  # org.bluez.GattCharacteristic1
    fido_status_notify_listen: ProxyInterface  # org.freedesktop.DBus.Properties
    max_msg_size: int

    def __init__(self, device: ProxyInterface, device_id: str):
        self.device = device
        self.device_id = device_id
        self.max_msg_size = 0

    async def connect(self, handler):
        if not self.connected:
            logging.info("START CONNECT")
            bus: MessageBus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            # Must connect at least once to be able to get all the characteristics
            await self.device.call_connect()
            logging.info("connected")
            # Hard code char ids or adaptive?
            control_point_length_proxy = bus.get_proxy_object('org.bluez', self.device_id + '/service0019/char001f', await bus.introspect('org.bluez', self.device_id + '/service0019/char001f'))
            control_point_length = control_point_length_proxy.get_interface('org.bluez.GattCharacteristic1')

            status_proxy = bus.get_proxy_object('org.bluez', self.device_id + '/service0019/char001c',  await bus.introspect('org.bluez', self.device_id + '/service0019/char001c'))
            status_characteristic = status_proxy.get_interface('org.bluez.GattCharacteristic1')
            notify_properties = status_proxy.get_interface('org.freedesktop.DBus.Properties')

            control_point_proxy = bus.get_proxy_object('org.bluez', self.device_id + '/service0019/char001a', await bus.introspect('org.bluez', self.device_id + '/service0019/char001a'))
            control_point = control_point_proxy.get_interface('org.bluez.GattCharacteristic1')

            logging.info("get size")
            self.max_msg_size = int.from_bytes(bytes(await control_point_length.call_read_value({})), "big")
            logging.info(f"size: {self.max_msg_size}")
            self.fido_control_point = control_point
            self.fido_status = status_characteristic
            self.fido_status_notify_listen = notify_properties
            self.connected = True
            await self.listen_to_notify(handler)

    async def write_data(self, payload):
        logging.info("Starting write data")
        while not self.connected:
            logging.info("Waiting to connect")
            await asyncio.sleep(1)

        logging.info("Connection complete")
        await self.fido_control_point.call_write_value(payload, {})

    async def listen_to_notify(self, handler):
        # self.fido_status_notify_listen.on_properties_changed(partial(notify_message, self.fido_status))
        logging.info("Setting up listener")
        # await self.fido_status.call_stop_notify()
        self.fido_status_notify_listen.on_properties_changed(partial(notify_message, handler))
        logging.info("Listener ready")
        await self.fido_status.call_start_notify()
        logging.info("Notify active")

    async def disconnect(self):
        await self.fido_status.call_stop_notify()
        await self.device.call_disconnect()
        self.connected = False
