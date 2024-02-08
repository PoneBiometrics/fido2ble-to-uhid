import enum


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