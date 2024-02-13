import asyncio
import logging
import struct
from random import randint
from typing import List

import uhid

from CMD import CTAPHID_CAPABILITIES, CTAPHID_CMD, CTAPBLE_CMD
from CTAPBLEDevice import CTAPBLEDevice
from CTAPBLEHIDConnection import CTAPBLEDeviceConnection

CTAPHID_BROADCAST_CHANNEL = 0xFFFFFFFF


class CTAPHIDDevice:
    device: uhid.UHIDDevice
    ble_devices: dict[str, CTAPBLEDevice]
    channels_to_state: dict[int, CTAPBLEDeviceConnection] = {}

    hid_packet_size: int = 64
    channel: int = 0
    hid_command: CTAPHID_CMD = CTAPHID_CMD.CANCEL
    hid_buffer: bytes = b""
    hid_total_length = 0
    hid_seq = -1

    fidoControlPointLength: int = 60
    ble_command: CTAPBLE_CMD = CTAPBLE_CMD.CANCEL
    ble_buffer: bytes = b""
    ble_total_length = 0
    ble_seq = -1

    nonce = 0

    reference_count = 0
    """Number of open handles to the device: clear state when it hits zero."""

    def __init__(self, ble_devices):
        # TODO: Check all BLE paired devices and announce these instead of a generic catch all device
        # This could then also include the proper name, VID, PID and so on
        self.ble_devices = ble_devices
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
            physical_name="Test Device"
        )

        self.device.receive_open = self.process_open
        self.device.receive_close = self.process_close
        self.device.receive_output = self.process_process_hid_message

    async def start(self):
        logging.info("USB start init")
        await self.device.wait_for_start_asyncio()
        logging.info("USB start done")

    def process_open(self):
        self.reference_count += 1

    def process_close(self):
        self.reference_count -= 1
        '''
        if self.reference_count == 0: 
            for _, connection in self.channels_to_state.items():
                asyncio.create_task(connection.close())
            self.channels_to_state = {}
            '''

    async def handle_init(self, channel, buffer: bytes):  # async?
        logging.info(f"hid init: channel={'%X' % channel} buffer={buffer}")
        if channel == CTAPHID_BROADCAST_CHANNEL and len(buffer) == 8:
            logging.info("Broadcast")
            # https://fidoalliance.org/specs/fido-v2.1-rd-20210309/fido-client-to-authenticator-protocol-v2.1-rd-20210309.html#usb-channels
            new_channel = randint(1, CTAPHID_BROADCAST_CHANNEL - 1)
            self.channel = new_channel
            self.nonce = buffer

            await self.send_init_reply(buffer, CTAPHID_BROADCAST_CHANNEL)

            logging.info("scanning for BLE devices now")

            self.channels_to_state[new_channel] = CTAPBLEDeviceConnection.create(
                self.handle_ble_message, self.ble_devices, new_channel
            )

        elif buffer == self.nonce:
            logging.info("Reuse")
            await self.send_init_reply(buffer, self.channel)
            # ble_device = self.ble_device

            # if ble_device is None:
            #    return None

            await self.channels_to_state[self.channel].connect()

    async def send_init_reply(self, nonce: bytes, channel: int):
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
            channel=channel
        )
        pass

    async def send_hid_message(self, command: CTAPHID_CMD, payload: bytes, channel: int = None):
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

            logging.info("SENDING")
            self.device.send_input(response)

            offset_start += capacity
            seq += 1
            
    def process_process_hid_message(
            self, buffer: list[int], report_type: uhid._ReportType
    ) -> None:
        logging.info("GOT MESSAGE")
        # output_report = buffer[0]
        received_data = bytes(buffer[1:])
        channel, cmd_or_seq = struct.unpack(">IB", received_data[0:5])
        # continuation = cmd_or_seq & 0x80 != 0
        cmd_or_seq = cmd_or_seq & 0x7F

        if channel == CTAPHID_BROADCAST_CHANNEL and cmd_or_seq == CTAPHID_CMD.INIT:
            asyncio.gather(self.handle_init(channel, received_data[7: 7 + 8]))
        else:
            self.handle_hid_message(channel, received_data[4:])

        # TODO Handling unkown channels
        # TODO Handling unknown commands

    def handle_hid_message(self, channel, payload_without_channel):
        (cmd_or_seq,) = struct.unpack(">B", payload_without_channel[0:1])
        continuation = cmd_or_seq & 0x80 == 0
        cmd_or_seq = cmd_or_seq & 0x7F

        if not continuation:
            self.hid_command = CTAPHID_CMD(cmd_or_seq)
            (self.hid_total_length,) = struct.unpack(">H", payload_without_channel[1:3])
            self.hid_seq = -1
            self.hid_buffer = payload_without_channel[3: 3 + self.hid_total_length]
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
            asyncio.create_task(self.hid_finish_receiving(channel))

    async def hid_finish_receiving(self, channel):
        logging.info(f"hid rx: command={self.hid_command.name} payload={self.hid_buffer.hex()}")
        while not self.channels_to_state[channel].ready():
            await asyncio.sleep(0.5)
        if self.hid_command == CTAPHID_CMD.CBOR:
            await self.send_ble_message(channel, CTAPBLE_CMD.MSG, self.hid_buffer)
        elif self.hid_command == CTAPHID_CMD.CANCEL:
            await self.send_ble_message(channel, CTAPBLE_CMD.CANCEL, self.hid_buffer)
        elif self.hid_command == CTAPHID_CMD.ERROR:
            # this should not happen, as the error is sent from the fido2 device via BLE, not from the relying party.
            await self.send_ble_message(channel, CTAPBLE_CMD.ERROR, self.hid_buffer)
        elif self.hid_command == CTAPHID_CMD.PING:
            await self.send_ble_message(channel, CTAPBLE_CMD.PING, self.hid_buffer)
        elif self.hid_command in (CTAPHID_CMD.INIT, CTAPHID_CMD.WINK, CTAPHID_CMD.MSG, CTAPHID_CMD.LOCK):
            # TODO
            pass

    def handle_ble_message(self, payload):
        logging.info(f"Handling BLE payload {payload.hex()}")
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
        self.channels_to_state[self.channel].keep_alive()
        if self.ble_command == CTAPBLE_CMD.MSG:
            await self.send_hid_message(CTAPHID_CMD.CBOR, self.ble_buffer)
        elif self.ble_command == CTAPBLE_CMD.KEEPALIVE:
            await self.send_hid_message(CTAPHID_CMD.KEEPALIVE, self.ble_buffer)
        elif self.ble_command == CTAPBLE_CMD.ERROR:
            await self.send_hid_message(CTAPHID_CMD.ERROR, self.ble_buffer)
        elif self.ble_command == CTAPBLE_CMD.PING:
            await self.send_hid_message(CTAPHID_CMD.PING, self.ble_buffer)
        elif self.ble_command == CTAPBLE_CMD.CANCEL:
            # Unsure if this case can happen, the cancel command comes from the relying party, not from the FIDO device
            await self.send_hid_message(CTAPHID_CMD.CANCEL, self.ble_buffer)
        else:
            pass
        self.ble_command = CTAPBLE_CMD.CANCEL
        self.ble_total_length = 0
        self.ble_buffer = bytes()
        self.ble_seq = -1

    async def send_ble_message(self, channel, command: CTAPBLE_CMD, payload:bytes):
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

            await self.channels_to_state[channel].ble_device.write_data(response)

            offset_start += capacity
            seq += 1
