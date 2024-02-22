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