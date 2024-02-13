#!/usr/bin/env python
import asyncio
import logging
from functools import partial
from dbus_fast import BusType
from dbus_fast.aio import ProxyInterface, MessageBus


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
    handler = None

    def __init__(self, device: ProxyInterface, device_id: str):
        self.device = device
        self.device_id = device_id
        self.max_msg_size = 0

    async def connect(self, handler):
        if self.max_msg_size == 0: # If we know Max Msg we have done this at least once. Don't want to redo it
            self.handler = partial(notify_message, handler)
            logging.info("START CONNECT")
            bus: MessageBus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            # Must connect at least once to be able to get all the characteristics
            # We might need to refresh through managed objects. This throws error first time on boot
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
            await self.listen_to_notify()
        else:
            logging.info(f"Device already connected: {self.device_id}")
            await self.reconnect()

        return self

    async def reconnect(self):
        await self.device.call_connect()
        self.connected = True
        await self.listen_to_notify()

    async def disconnect(self):
        self.fido_status_notify_listen.off_properties_changed(self.handler)
        await self.fido_status.call_stop_notify()
        await self.device.call_disconnect()
        self.connected = False

    async def write_data(self, payload):
        logging.info("Starting write data")
        while not self.connected:
            logging.info("Waiting to connect")
            await asyncio.sleep(1)

        logging.info("Connection complete")
        await self.fido_control_point.call_write_value(payload, {})

    async def listen_to_notify(self):
        logging.info("Setting up listener")
        self.fido_status_notify_listen.on_properties_changed(self.handler)
        logging.info("Listener ready")
        await self.fido_status.call_start_notify()
        logging.info("Notify active")
