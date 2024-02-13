import asyncio
import logging
from asyncio import FIRST_COMPLETED
from typing import Callable

from CTAPBLEDevice import CTAPBLEDevice


class CTAPBLEDeviceConnection:
    timeout = 5000
    ble_devices: dict[str, CTAPBLEDevice]
    ble_device: CTAPBLEDevice = None
    channel: bytes
    handler: Callable

    @classmethod
    def create(cls, handle_message, ble_devices: dict[str, CTAPBLEDevice], channel):
        logging.info(f"Connecting to {ble_devices}")
        self = cls()
        self.handler = handle_message
        self.ble_devices = ble_devices
        self.channel = channel
        asyncio.create_task(self.connect())
        # noinspection PyAsyncCall
        return self

    async def disconnect(self):
        await self.ble_device.disconnect()
        # noinspection PyTypeChecker
        self.ble_device = None

    async def connect(self):
        tasks = []
        for device_id in self.ble_devices:
            logging.info("Sending to even queue")
            tasks.append(asyncio.ensure_future(self.ble_devices[device_id].connect(self.handler)))

        logging.info("All sent")
        done, pending = await asyncio.wait(tasks, return_when=FIRST_COMPLETED)
        self.ble_device = done.pop().result()

        for task in pending:
            task.cancel()

        self.timeout = 5000
        # noinspection PyAsyncCall
        asyncio.create_task(self.check_timeout())
        logging.info(f"Connected to {self.ble_devices}")

    def ready(self):
        if self.ble_device is not None:
            return True
        return False

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

