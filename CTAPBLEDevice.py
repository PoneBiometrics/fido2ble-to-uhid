#!/usr/bin/env python
import asyncio
import logging
import struct
from functools import partial
from dbus_fast import BusType
from dbus_fast.aio import ProxyInterface, MessageBus

from CMD import CTAPBLE_CMD


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
    timeout = 5000
    cached = False

    fido_control_point: ProxyInterface  # org.bluez.GattCharacteristic1
    fido_status: ProxyInterface  # org.bluez.GattCharacteristic1
    fido_status_notify_listen: ProxyInterface  # org.freedesktop.DBus.Properties
    max_msg_size: int
    handler = None

    def __init__(self, device: ProxyInterface, device_id: str, cached: bool):
        self.device = device
        self.device_id = device_id
        self.max_msg_size = 0
        self.cached = cached

    async def connect(self, handler):
        if self.max_msg_size == 0: # If we know Max Msg we have done this at least once. Don't want to redo it
            self.handler = partial(notify_message, handler)
            bus: MessageBus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            logging.debug(f"Attempting to connect to {self.device_id}")
            # noinspection PyUnresolvedReferences
            await self.device.call_connect()

            # If the OS lacked data on this before we need to re-fetch data and reconnect but has to be a better way somehow
            if not self.cached:
                await self.device.call_disconnect()
                device_introspect = await bus.introspect('org.bluez', self.device_id)
                device_proxy = bus.get_proxy_object('org.bluez', self.device_id, device_introspect)
                self.device = device_proxy.get_interface('org.bluez.Device1')
                self.cached = True
                await self.device.call_connect()

            # Hardcode char ids or adaptive? char001f, char001c and char001a on service0019 always seem to reflect what we need, not sure why
            control_point_length_proxy = bus.get_proxy_object('org.bluez', self.device_id + '/service0019/char001f', await bus.introspect('org.bluez', self.device_id + '/service0019/char001f'))
            control_point_length = control_point_length_proxy.get_interface('org.bluez.GattCharacteristic1')

            status_proxy = bus.get_proxy_object('org.bluez', self.device_id + '/service0019/char001c', await bus.introspect('org.bluez', self.device_id + '/service0019/char001c'))
            status_characteristic = status_proxy.get_interface('org.bluez.GattCharacteristic1')
            notify_properties = status_proxy.get_interface('org.freedesktop.DBus.Properties')

            control_point_proxy = bus.get_proxy_object('org.bluez', self.device_id + '/service0019/char001a', await bus.introspect('org.bluez', self.device_id + '/service0019/char001a'))
            control_point = control_point_proxy.get_interface('org.bluez.GattCharacteristic1')
            # noinspection PyUnresolvedReferences
            self.max_msg_size = int.from_bytes(bytes(await control_point_length.call_read_value({})), "big")
            logging.debug(f"size: {self.max_msg_size}")

            self.fido_control_point = control_point
            self.fido_status = status_characteristic
            self.fido_status_notify_listen = notify_properties
            self.connected = True
            await self.listen_to_notify()
        else:
            logging.debug(f"Device already connected: {self.device_id}")
            await self.reconnect()

        self.timeout = 5000  # Way higher than should be until we fix keep alive interval on card
        logging.debug(f"Connection complete: {self.device_id}")
        return self

    async def reconnect(self):
        # noinspection PyUnresolvedReferences
        await self.device.call_connect()
        self.connected = True
        await self.listen_to_notify()

    async def disconnect(self):
        # noinspection PyUnresolvedReferences
        logging.debug(f"Disconnecting: {self.device_id}")
        self.fido_status_notify_listen.off_properties_changed(self.handler)
        # noinspection PyUnresolvedReferences
        await self.fido_status.call_stop_notify()
        # noinspection PyUnresolvedReferences
        await self.device.call_disconnect()
        self.connected = False

    async def write_data(self, payload):
        while not self.connected:
            logging.debug("Waiting to connect")
            await asyncio.sleep(0.5)

        # noinspection PyUnresolvedReferences
        await self.fido_control_point.call_write_value(payload, {})

    async def listen_to_notify(self):
        # noinspection PyUnresolvedReferences
        self.fido_status_notify_listen.on_properties_changed(self.handler)
        # noinspection PyUnresolvedReferences
        await self.fido_status.call_start_notify()

    async def send_ble_message(self, command: CTAPBLE_CMD, payload:bytes):
        logging.debug(f"ble tx: command={command.name} device={self.device_id} payload={payload.hex()}")
        offset_start = 0
        seq = 0
        while offset_start < len(payload) or offset_start == 0:
            if seq == 0:
                capacity = self.max_msg_size - 3
                response = struct.pack(">BH", 0x80 | command, len(payload))
            else:
                capacity = self.max_msg_size - 1
                response = struct.pack(">B", seq - 1)
            response += payload[offset_start : (offset_start + capacity)]

            await self.write_data(response)

            offset_start += capacity
            seq += 1

    def get_connected_ble(self):
        if self.connected:
            return self
        return None

    def keep_alive(self):
        self.timeout = 5000
