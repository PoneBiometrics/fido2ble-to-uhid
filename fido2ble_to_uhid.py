#!/usr/bin/env python

import asyncio
import enum
import logging
from pprint import pprint

from dbus_fast import BusType
from dbus_fast.aio import MessageBus

from CTAPBLEDevice import CTAPBLEDevice
from CTAPHIDDevice import CTAPHIDDevice

FIDO_SERVICE_UUID = "0000fffd-0000-1000-8000-00805f9b34fb"
FIDO_CONTROL_POINT_UUID = "f1d0fff1-deaa-ecee-b42f-c9ba7ed623bb"
FIDO_STATUS_UUID = "f1d0fff2-deaa-ecee-b42f-c9ba7ed623bb"
FIDO_CONTROL_POINT_LENGTH_UUID = "f1d0fff3-deaa-ecee-b42f-c9ba7ed623bb"
FIDO_SERVICE_REVISION_BITFIELD_UUID = "f1d0fff4-deaa-ecee-b42f-c9ba7ed623bb"


class CTAP_STATUS(enum.IntEnum):
    """Status codes

    See: https://fidoalliance.org/specs/fido-v2.1-rd-20210309/fido-client-to-authenticator-protocol-v2.1-rd-20210309.html#error-responses
    """

    CTAP1_ERR_INVALID_COMMAND = 0x01
    """The command is not a valid CTAP command."""

    CTAP1_ERR_INVALID_SEQ = 0x04
    """Invalid message sequencing."""
    CTAP1_ERR_INVALID_CHANNEL = 0x0B
    """Command not allowed on this cid."""

    CTAP1_ERR_OTHER = 0x7F
    """Other unspecified error."""


logging.basicConfig(level=logging.INFO)
logging.getLogger("UHIDDevice").setLevel(logging.ERROR)


async def find_fido() -> dict[str, CTAPBLEDevice]:
    bus: MessageBus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    bluez_introspect = await bus.introspect(
         "org.bluez", '/'
    )

    dbus_proxy = bus.get_proxy_object('org.bluez', '/', bluez_introspect)
    dbus_managed_objects = await dbus_proxy.get_interface("org.freedesktop.DBus.ObjectManager").call_get_managed_objects()

    fido_devices = {}

    for device_path in dbus_managed_objects:
        if 'org.bluez.Device1' in dbus_managed_objects[device_path]:
            if dbus_managed_objects[device_path]['org.bluez.Device1']['Paired'].value:
                logging.info(f"Found {device_path} as paired")
                if 'UUIDs' in dbus_managed_objects[device_path]['org.bluez.Device1']:
                    for uuid in dbus_managed_objects[device_path]['org.bluez.Device1']['UUIDs'].value:
                        if uuid == FIDO_SERVICE_UUID:
                            logging.info(f"Found {uuid} in device")
                            device_proxy = bus.get_proxy_object('org.bluez', device_path,
                                                                await bus.introspect('org.bluez', device_path))
                            device1 = device_proxy.get_interface('org.bluez.Device1')
                            fido_devices[device_path] = CTAPBLEDevice(device1, device_path)
                            '''
                if 'ServiceData' in dbus_managed_objects[device_path]['org.bluez.Device1']:
                    if FIDO_SERVICE_UUID in dbus_managed_objects[device_path]['org.bluez.Device1']['ServiceData'].value.keys():
                        logging.info(f"Found through ServiceData")
                        device_proxy = bus.get_proxy_object('org.bluez', device_path,
                                                            await bus.introspect('org.bluez', device_path))
                        device1 = device_proxy.get_interface('org.bluez.Device1')
                        fido_devices[device_path] = CTAPBLEDevice(device1, device_path)
                        '''
    return fido_devices


async def start_system():
    fido_devices: dict[str, CTAPBLEDevice] = await find_fido()
    hid_devices = []
    for fido_device in fido_devices:
        hid = CTAPHIDDevice(fido_devices[fido_device])
        asyncio.create_task(hid.start())
        hid_devices.append(hid)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(start_system())
        loop.run_forever()  # run queued dispatch tasks
        loop.close()
    except KeyboardInterrupt:
        loop.close()
