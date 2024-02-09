import asyncio
import logging
from typing import Callable

from CTAPBLEDevice import CTAPBLEDevice


class CTAPBLEDeviceConnection:
    timeout = 5000
    ble_device: CTAPBLEDevice
    channel: bytes
    handler: Callable

    @classmethod
    async def create(cls, handle_message, ble_device: CTAPBLEDevice, channel):
        logging.info(f"Connecting to {ble_device}")
        self = cls()
        self.handler = handle_message
        self.ble_device = ble_device
        self.channel = channel
        await ble_device.connect(self.handler)
        logging.info(f"Connected to {ble_device}")
        asyncio.create_task(self.check_timeout())
        return self

    async def disconnect(self):
        await self.ble_device.disconnect(self.handler)


    async def reconnect(self):
        logging.info("RECONNECT")
        await self.ble_device.connect(self.handler)
        self.timeout = 5000
        asyncio.create_task(self.check_timeout())

    def keep_alive(self):
        logging.info("Timeout reset")
        self.timeout = 5000

    async def check_timeout(self):
        while self.timeout > 0:
            logging.info(f"Timeout {self.timeout}")
            self.timeout -= 100
            await asyncio.sleep(0.1)

        logging.info("DISCONNECTING")
        await self.disconnect()

