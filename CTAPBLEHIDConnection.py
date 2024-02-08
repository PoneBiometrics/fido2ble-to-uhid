from CTAPBLEDevice import CTAPBLEDevice


class CTAPBLEDeviceConnection:

    @classmethod
    async def create(cls, hid_device, ble_device: CTAPBLEDevice, channel, nonce):
        self = cls()
        self.ble_device = ble_device
        await ble_device.connect(hid_device.handle_ble_message)
        self.hid_device = hid_device
        self.channel = channel
        await hid_device.send_init_reply(nonce)
        return self
