#!/usr/bin/env python

import asyncio
import enum
import logging

import uhid
import struct
from typing import Optional, Callable, Dict, Tuple, List
from random import randint
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.scanner import AdvertisementData

FIDO_SERVICE_UUID = "0000fffd-0000-1000-8000-00805f9b34fb"
FIDO_CONTROL_POINT_UUID = "f1d0fff1-deaa-ecee-b42f-c9ba7ed623bb"
FIDO_STATUS_UUID = "f1d0fff2-deaa-ecee-b42f-c9ba7ed623bb"
FIDO_CONTROL_POINT_LENGTH_UUID = "f1d0fff3-deaa-ecee-b42f-c9ba7ed623bb"
FIDO_SERVICE_REVISION_BITFIELD_UUID = "f1d0fff4-deaa-ecee-b42f-c9ba7ed623bb"

CTAPHID_BROADCAST_CHANNEL = 0xFFFFFFFF


class CTAPHID_CMD(enum.IntEnum):
    MSG = 0x03
    CBOR = 0x10
    INIT = 0x06
    PING = 0x01
    CANCEL = 0x11
    ERROR = 0x3F
    KEEPALIVE = 0x3B
    WINK = 0x08
    LOCK = 0x04

class CTAPHID_CAPABILITIES(enum.IntFlag):
    CAPABILITY_WINK = 0x01  # not defined for BLE
    CAPABILITY_CBOR = 0x04  # 
    CAPABILITY_NMSG = 0x08  # PONE OffPAD currently only supports FIDO2, not U2F, so this will be set for now
                            # TODO: check if we can get that info from the device itself

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


class CTAPBLEDeviceConnection:
    ble_client: BleakClient = None
    fidoControlPoint: BleakGATTCharacteristic = None
    fidoControlPointLength: int = 0
    ble_command: CTAPBLE_CMD = CTAPBLE_CMD.CANCEL
    ble_buffer: bytes = b""
    ble_total_length = 0
    ble_seq = -1

    uhid_device: uhid.UHIDDevice = None
    hid_packet_size: int = 64
    channel: int = 0
    hid_command: CTAPHID_CMD = CTAPHID_CMD.CANCEL
    hid_buffer: bytes = b""
    hid_total_length = 0
    hid_seq = -1

    @classmethod
    async def create(cls, uhid_device, ble_device, channel, nonce):
        self = cls()
        await self.connect_to_ble(ble_device)
        self.uhid_device = uhid_device
        self.channel = channel
        await self.send_init_reply(nonce)
        return self

    async def connect_to_ble(self, device):
        # do the general setup

        client = BleakClient(device)
        await client.connect()
        # https://fidoalliance.org/specs/fido-v2.0-id-20180227/fido-client-to-authenticator-protocol-v2.0-id-20180227.html#ble-protocol-overview

        fidoService = client.services.get_service(FIDO_SERVICE_UUID)
        fidoServiceRevisionBitfield = fidoService.get_characteristic(
            FIDO_SERVICE_REVISION_BITFIELD_UUID
        )
        fidoControlPointLength = fidoService.get_characteristic(
            FIDO_CONTROL_POINT_LENGTH_UUID
        )
        fidoStatus = fidoService.get_characteristic(FIDO_STATUS_UUID)
        self.chosen_device = (
            client,
            fidoService.get_characteristic(FIDO_CONTROL_POINT_UUID),
        )

        # read fidoServiceRevisionBitfield
        service_revision = await client.read_gatt_char(fidoServiceRevisionBitfield)
        logging.info(f"service revision: 0x{service_revision.hex()}")

        # set fidoServiceRevisionBitfield 0x20
        logging.info("setting to 0x20")
        await client.write_gatt_char(fidoServiceRevisionBitfield, b"\x20")

        # read fidoControlPointLength
        control_point_length = struct.unpack(
            ">H", await client.read_gatt_char(fidoControlPointLength)
        )[0]
        logging.info(f"fidoControlPointLength: {control_point_length}")

        # fill fidoControlPoint and Length values
        self.fidoControlPoint = fidoService.get_characteristic(FIDO_CONTROL_POINT_UUID)
        self.ble_client = client
        self.fidoControlPointLength = control_point_length

        # set up return path to hid callback
        # register for notifications on fidoStatus
        await client.start_notify(fidoStatus, self.handle_ble_message)

    async def send_init_reply(self, nonce: bytes):
        await self.send_hid_message(
            CTAPHID_CMD.INIT,
            struct.pack(
                ">8sIBBBBB",
                nonce,
                self.channel,
                2,  # protocol version, currently fixed at 2
                0,  # device version major, TODO get from devie
                1,  # device version minor, TODO get from device
                1,  # device version build/point, TODO get from device
                CTAPHID_CAPABILITIES.CAPABILITY_CBOR | CTAPHID_CAPABILITIES.CAPABILITY_NMSG, # these are the same for all BLE FIDO2 devices
            ),
            channel=CTAPHID_BROADCAST_CHANNEL,
        )
        pass

    def handle_ble_message(self, _, payload):
        (cmd_or_seq,) = struct.unpack(">B", payload[0:1])
        continuation = cmd_or_seq & 0x80 == 0
        cmd_or_seq = cmd_or_seq # no adding of & 0x7F, as the command definitions include 0x80 for some reason in BLE

        if not continuation:
            self.ble_command = CTAPBLE_CMD(cmd_or_seq)
            (self.ble_total_length,) = struct.unpack(">H", payload[1:3])
            self.ble_buffer = payload[3 : 3 + self.ble_total_length]
            self.ble_seq = -1
        else:
            payload = payload[1:]
            # if cmd_or_seq != self.ble_seq + 1:
            #     self.handle_cancel(channel)
            #     self.send_error(channel, CTAP_STATUS.CTAP1_ERR_INVALID_SEQ)
            #     return
            remaining = self.ble_total_length - len(self.ble_buffer)
            self.ble_buffer += payload[:remaining]
            self.ble_seq = cmd_or_seq
        if self.ble_total_length == len(self.ble_buffer):
            asyncio.create_task(self.ble_finish_receiving())

    async def ble_finish_receiving(self):
        logging.info(f"ble rx: command={self.ble_command.name} payload={self.ble_buffer.hex()}")
        if self.ble_command == CTAPBLE_CMD.MSG:
            await self.send_hid_message(CTAPHID_CMD.CBOR, self.ble_buffer)
        elif self.ble_command == CTAPBLE_CMD.KEEPALIVE:
            await self.send_hid_message(CTAPHID_CMD.KEEPALIVE, self.ble_buffer)
        elif self.ble_command == CTAPBLE_CMD.ERROR:
            await self.send_hid_message(CTAPHID_CMD.ERROR, self.ble_buffer)
        elif self.ble_command == CTAPBLE_CMD.PING:
            await self.send_hid_message(CTAPHID_CMD.PING, self.ble_buffer)
        elif self.ble_command == CTAPBLE_CMD.CANCEL:
            # not sure if this case can happen, as the cancel command comes from the relying party, not from the FIDO device
            await self.send_hid_message(CTAPHID_CMD.CANCEL, self.ble_buffer)
        else:
            pass
        self.ble_command = CTAPBLE_CMD.CANCEL
        self.ble_total_length = 0
        self.ble_buffer = bytes()
        self.ble_seq = -1

    async def send_ble_message(self, command: CTAPBLE_CMD, payload:bytes):
        logging.info(f"ble tx: command={command.name} payload={payload.hex()}")
        offset_start = 0
        seq = 0
        while offset_start < len(payload):
            if seq == 0:
                capacity = self.fidoControlPointLength - 3
                response = struct.pack(">BH", 0x80 | command, len(payload))
            else:
                capacity = self.fidoControlPointLength - 1
                response = struct.pack(">B", seq - 1)
            response += payload[offset_start : (offset_start + capacity)]

            await self.ble_client.write_gatt_char(self.fidoControlPoint, response)

            offset_start += capacity
            seq += 1

    async def send_hid_message(self, command:CTAPHID_CMD, payload: bytes, channel: int = None):
        logging.info(f"hid tx: command={command.name} payload={payload.hex()}")
        if channel is None:
            channel = self.channel
        offset_start = 0
        seq = 0
        while offset_start < len(payload):
            if seq == 0:
                capacity = self.hid_packet_size - 7
                response = struct.pack(">IBH", channel, 0x80 | command, len(payload))
            else:
                capacity = self.hid_packet_size - 5
                response = struct.pack(">IB", channel, seq - 1)
            response += payload[offset_start : (offset_start + capacity)]

            response += b"\0" * (self.hid_packet_size - len(response))

            self.uhid_device.send_input(response)

            offset_start += capacity
            seq += 1

    def handle_hid_message(self, payload_without_channel):
        (cmd_or_seq,) = struct.unpack(">B", payload_without_channel[0:1])
        continuation = cmd_or_seq & 0x80 == 0
        cmd_or_seq = cmd_or_seq & 0x7F

        if not continuation:
            self.hid_command = CTAPHID_CMD(cmd_or_seq)
            (self.hid_total_length,) = struct.unpack(">H", payload_without_channel[1:3])
            self.hid_seq = -1
            self.hid_buffer = payload_without_channel[3 : 3 + self.hid_total_length]
        else:
            if cmd_or_seq != self.hid_seq + 1:
                logging.info(f"dragons")
                # there be dragons: CTAP_STATUS.CTAP1_ERR_INVALID_SEQ
                return
            payload = payload_without_channel[1:]
            remaining = self.hid_total_length - len(self.hid_buffer)
            self.hid_buffer += payload[:remaining]
            self.hid_seq = cmd_or_seq
        if self.hid_total_length == len(self.hid_buffer):
            asyncio.create_task(self.hid_finish_receiving())

    async def hid_finish_receiving(self):
        logging.info(f"hid rx: command={self.hid_command.name} payload={self.hid_buffer.hex()}")
        if self.hid_command == CTAPHID_CMD.CBOR:
            await self.send_ble_message(CTAPBLE_CMD.MSG, self.hid_buffer)
        elif self.hid_command == CTAPHID_CMD.CANCEL:
            await self.send_ble_message(CTAPBLE_CMD.CANCEL, self.hid_buffer)
        elif self.hid_command == CTAPHID_CMD.ERROR:
            # this should not happen, as the error is sent from the fido2 device via BLE, not from the relying party.
            await self.send_ble_message(CTAPBLE_CMD.ERROR, self.hid_buffer)
        elif self.hid_command == CTAPHID_CMD.PING:
            await self.send_ble_message(CTAPBLE_CMD.PING, self.hid_buffer)
        elif self.hid_command in (CTAPHID_CMD.INIT, CTAPHID_CMD.WINK, CTAPHID_CMD.MSG, CTAPHID_CMD.LOCK):
            # TODO
            pass

    async def close(self):
        await self.ble_client.disconnect()


class CTAPHIDDevice:
    device: uhid.UHIDDevice

    channels_to_state: Dict[int, CTAPBLEDeviceConnection] = {}

    reference_count = 0
    """Number of open handles to the device: clear state when it hits zero."""

    def __init__(self):
        # TODO: Check all BLE paired devices and announce these instead of a generic catch all device
        # This could then also include the proper name, VID, PID and so on

        self.device = uhid.UHIDDevice(
            vid=0xAAAA,
            pid=0xAAAA,  # these are the yubikey VID and PID. These need to change for prod.
            name="PONE Fido2BLE Proxy",
            report_descriptor=[
                0x06,
                0xD0,
                0xF1,  # Usage Page (FIDO alliance HID usage page)
                0x09,
                0x01,  # Usage (U2FHID usage for top-level collection)
                0xA1,
                0x01,  # Collection (Application)
                0x09,
                0x20,  #   Usage (Raw IN data report)
                0x15,
                0x00,  #   Logical Minimum (0)
                0x26,
                0xFF,
                0x00,  #   Logical Maximum (255)
                0x75,
                0x08,  #   Report Size (8)
                0x95,
                0x40,  #   Report Count (64)
                0x81,
                0x02,  #   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
                0x09,
                0x21,  #   Usage (Raw OUT data report)
                0x15,
                0x00,  #   Logical Minimum (0)
                0x26,
                0xFF,
                0x00,  #   Logical Maximum (255)
                0x75,
                0x08,  #   Report Size (8)
                0x95,
                0x40,  #   Report Count (64)
                0x91,
                0x02,  #   Output (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position,Non-volatile)
                0xC0,  # End Collection
            ],
            backend=uhid.AsyncioBlockingUHID,
            physical_name="Test Device",
        )

        self.device.receive_open = self.process_open
        self.device.receive_close = self.process_close
        self.device.receive_output = self.process_process_hid_message

    async def start(self):
        await self.device.wait_for_start_asyncio()

    def process_open(self):
        self.reference_count += 1

    def process_close(self):
        self.reference_count -= 1
        if self.reference_count == 0:
            for _, connection in self.channels_to_state.items():
                asyncio.create_task(connection.close())
            self.channels_to_state = {}

    def process_process_hid_message(
        self, buffer: List[int], report_type: uhid._ReportType
    ) -> None:
        # output_report = buffer[0]
        received_data = bytes(buffer[1:])
        channel, cmd_or_seq = struct.unpack(">IB", received_data[0:5])
        # continuation = cmd_or_seq & 0x80 != 0
        cmd_or_seq = cmd_or_seq & 0x7F

        if channel == CTAPHID_BROADCAST_CHANNEL and cmd_or_seq == CTAPHID_CMD.INIT:
            asyncio.create_task(self.handle_init(channel, received_data[7 : 7 + 8]))
        else:
            if channel in self.channels_to_state:
                self.channels_to_state[channel].handle_hid_message(received_data[4:])
            else:
                logging.error(f"requested key {channel}, however only available channels are: {[i for i in self.channels_to_state.keys()]}")

        # TODO Handling unkown channels
        # TODO Handling unknown commands

    async def handle_init(self, channel, buffer: bytes):  # async?
        if channel == CTAPHID_BROADCAST_CHANNEL and len(buffer) == 8:
            # https://fidoalliance.org/specs/fido-v2.1-rd-20210309/fido-client-to-authenticator-protocol-v2.1-rd-20210309.html#usb-channels
            new_channel = randint(1, CTAPHID_BROADCAST_CHANNEL - 1)

            logging.info("scanning for BLE devices now")
            ble_device = await self.scan_for_fido2ble()

            if ble_device is None:
                return None

            self.channels_to_state[new_channel] = await CTAPBLEDeviceConnection.create(
                self.device, ble_device, new_channel, buffer
            )


    async def scan_for_fido2ble(self):
        stop_event = asyncio.Event()
        found_devices: List[BLEDevice] = []

        def callback(device: BLEDevice, advertising_data: AdvertisementData):
            if FIDO_SERVICE_UUID in advertising_data.service_uuids:
                logging.info(
                    f"dev {device.address} services {advertising_data.service_uuids}"
                )
                found_devices.append(device)
                stop_event.set()
            pass

        # alternatively, I could work with find_device_by_filter
        # this currently does not have a timeout
        async with BleakScanner(callback) as scanner:
            await stop_event.wait()
        # currently only dealing with one available BLE device
        device = found_devices[0]
        return device


async def run_device() -> None:
    device = CTAPHIDDevice()
    await device.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_device())  # create device
    loop.run_forever()  # run queued dispatch tasks
