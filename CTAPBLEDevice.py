from functools import partial

from dbus_fast import BusType
from dbus_fast.aio import ProxyInterface, MessageBus


def notify_message(fido_status, interface_name, changed_properties, invalidated_properties):
    # Add check here for message length and read until done then close connection
    # Should bind this with USB as well as just direct translate.
    # Will most likely need read whole message to repackage as USB has different size
    if ('Value' in changed_properties):
        print(''.join('{:02x}'.format(x) for x in changed_properties['Value'].value))


class CTAPBLEDevice:
    device: ProxyInterface  # org.bluez.Device1
    device_id: str

    fido_control_point: ProxyInterface  # org.bluez.GattCharacteristic1
    fido_status: ProxyInterface  # org.bluez.GattCharacteristic1
    fido_status_notify_listen: ProxyInterface  # org.freedesktop.DBus.Properties
    max_msg_size: int

    def __init__(self, device: ProxyInterface, device_id: str):
        self.device = device
        self.device_id = device_id
        self.max_msg_size = 0

    async def connect(self, bus):
        # Must connect at least once to be able to get all the characteristics
        await self.device.call_connect()
        #Hard code char ids or adaptive?
        control_point_length_proxy = bus.get_proxy_object('org.bluez', self.device_id + '/service0019/char001f', await bus.introspect('org.bluez', self.device_id + '/service0019/char001f'))
        control_point_length = control_point_length_proxy.get_interface('org.bluez.GattCharacteristic1')

        status_proxy = bus.get_proxy_object('org.bluez', self.device_id + '/service0019/char001c',  await bus.introspect('org.bluez', self.device_id + '/service0019/char001c'))
        status_characteristic = status_proxy.get_interface('org.bluez.GattCharacteristic1')
        notify_properties = status_proxy.get_interface('org.freedesktop.DBus.Properties')

        control_point_proxy = bus.get_proxy_object('org.bluez', self.device_id + '/service0019/char001a', await bus.introspect('org.bluez', self.device_id + '/service0019/char001a'))
        control_point = control_point_proxy.get_interface('org.bluez.GattCharacteristic1')

        self.max_msg_size = int.from_bytes(bytes(await control_point_length.call_read_value({})), "big")
        self.fido_control_point = control_point
        self.fido_status = status_characteristic
        self.fido_status_notify_listen = notify_properties

    async def write_data(self, payload):
        if self.max_msg_size > 0:
            await self.connect(await MessageBus(bus_type=BusType.SYSTEM).connect())
            await self.fido_control_point.call_write_value(payload, {})
        else:
            await self.device.call_connect()
            await self.listen_to_notify()
            await self.fido_control_point.call_write_value(payload, {})

    async def listen_to_notify(self):
        self.fido_status_notify_listen.on_properties_changed(partial(notify_message, self.fido_status))
        await self.fido_status.call_start_notify()
