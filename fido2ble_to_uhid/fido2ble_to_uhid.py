#!/usr/bin/env python

import asyncio
import logging

from .vendored.dbus_fast import BusType
from .vendored.dbus_fast.aio import MessageBus

from .CTAPBLEDevice import CTAPBLEDevice, find_characteristics
from .CTAPHIDDevice import CTAPHIDDevice

FIDO_SERVICE_UUID = "0000fffd-0000-1000-8000-00805f9b34fb"
FIDO_CONTROL_POINT_UUID = "f1d0fff1-deaa-ecee-b42f-c9ba7ed623bb"
FIDO_STATUS_UUID = "f1d0fff2-deaa-ecee-b42f-c9ba7ed623bb"
FIDO_CONTROL_POINT_LENGTH_UUID = "f1d0fff3-deaa-ecee-b42f-c9ba7ed623bb"
FIDO_SERVICE_REVISION_BITFIELD_UUID = "f1d0fff4-deaa-ecee-b42f-c9ba7ed623bb"

logging.basicConfig(level=logging.INFO)
logging.getLogger("UHIDDevice").setLevel(logging.ERROR)

async def create_device(device_path, dbus_managed_objects, bus) -> CTAPBLEDevice:
    device_proxy = bus.get_proxy_object('org.bluez', device_path, await bus.introspect('org.bluez', device_path))
    device1 = device_proxy.get_interface('org.bluez.Device1')
    cached = False
    for key in dbus_managed_objects:
        if key.startswith(device_path + '/'):
            cached = True
            break

    # Create a map to store characteristic paths
    characteristic_paths = {
        FIDO_CONTROL_POINT_UUID: None,
        FIDO_CONTROL_POINT_LENGTH_UUID: None,
        FIDO_STATUS_UUID: None,
    }

    await find_characteristics(device_path, dbus_managed_objects, characteristic_paths)
    control_point_path = characteristic_paths[FIDO_CONTROL_POINT_UUID]
    control_point_length_path = characteristic_paths[FIDO_CONTROL_POINT_LENGTH_UUID]
    status_path = characteristic_paths[FIDO_STATUS_UUID]
    return CTAPBLEDevice(device1, device_path, cached, control_point_path, control_point_length_path, status_path)


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
                if 'UUIDs' in dbus_managed_objects[device_path]['org.bluez.Device1']:
                    for uuid in dbus_managed_objects[device_path]['org.bluez.Device1']['UUIDs'].value:
                        if uuid == FIDO_SERVICE_UUID:
                            logging.debug(f"Found {device_path} as FIDO device")
                            fido_devices[device_path] = await create_device(device_path, dbus_managed_objects, bus)
                elif 'ServiceData' in dbus_managed_objects[device_path]['org.bluez.Device1']:
                    if FIDO_SERVICE_UUID in dbus_managed_objects[device_path]['org.bluez.Device1']['ServiceData'].value.keys():
                        logging.debug(f"Found {device_path} as FIDO device")
                        fido_devices[device_path] = await create_device(device_path, dbus_managed_objects, bus)
    return fido_devices


async def start_system():
    fido_devices: dict[str, CTAPBLEDevice] = await find_fido()
    hid_devices = []
    for fido_device in fido_devices:
        hid = CTAPHIDDevice(fido_devices[fido_device])
        # noinspection PyAsyncCall
        asyncio.create_task(hid.start())
        hid_devices.append(hid)

def main():
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(start_system())
        loop.run_forever()  # run queued dispatch tasks
        loop.close()
    except KeyboardInterrupt:
        loop.close()

if __name__ == "__main__":
    main()