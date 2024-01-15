# fido2ble-to-uhid
Bridging FIDO2 BLE devices to the HID bus via /dev/uhid so they can be used in browsers



## Dependencies on debian-based systems

```
apt install python3-bleak
pip install --break-system-packages uhid
```
We still have to work on proper packaging.


## Running it

Run the following command in a new shell:

```
./fido2ble_to_uhid.py
```

### Verifying that it runs

```
$ fido2-token -L
/dev/hidraw0: vendor=0xaaaa, product=0xaaaa ( )
$ fido2-token -I /dev/hidraw0
proto: 0x02
major: 0x00
minor: 0x01
build: 0x01
caps: 0x0c (nowink, cbor, nomsg)
version strings: FIDO_2_0, FIDO_2_1
extension strings: hmac-secret, credProtect
transport strings: ble
algorithms: es256 (public-key), rs256 (public-key)
aaguid: 69700f79d1fb472ebd9ba3a3b9a9eda0
options: rk, up, uv, noplat, noalwaysUv, credMgmt, clientPin, pinUvAuthToken, makeCredUvNotRqd
maxmsgsiz: 1024
maxcredcntlst: 0
maxcredlen: 0
maxlargeblob: 0
fwversion: 0x1
pin protocols: 1, 2
pin retries: 8
uv retries: 8
```

A complete registration cycle would look like this

```
echo credential challenge | openssl sha256 -binary | base64 > cred_param
echo my-party >> cred_param
echo my-user >> cred_param
dd if=/dev/urandom bs=1 count=32 | base64 >> cred_param
fido2-cred -M -i cred_param /dev/hidraw0 | fido2-cred -V -o cred


echo assertion challenge | openssl sha256 -binary | base64 > assert_param
echo my-party >> assert_param
head -1 cred >> assert_param
tail -n +2 cred > pubkey
fido2-assert -G -i assert_param /dev/hidraw0 | fido2-assert -V pubkey es256
```


### Notes

Once you run a command that will actively connect to the card, you need to press the button of the OFFPAD.
It currently only works, if the OFFPAD is paired but not connected via BLE. This is a limitation of the used library `BLEAK`.
However, this can be overcome by implementing the Bluetooth logic in `dbus_fast`

### Debugging FIDO2 Payload
```
INFO:root:scanning for BLE devices now
INFO:root:dev C9:E8:2B:06:B2:F0 services ['00001800-0000-1000-8000-00805f9b34fb', '00001801-0000-1000-8000-00805f9b34fb', '0000180a-0000-1000-8000-00805f9b34fb', '0000180f-0000-1000-8000-00805f9b34fb', '0000fffd-0000-1000-8000-00805f9b34fb', '5c050001-04fb-4d23-affd-179fc92c557f']
INFO:root:service revision: 0x20
INFO:root:setting to 0x20
INFO:root:fidoControlPointLength: 60
INFO:root:hid tx: command=INIT payload=18f6c3e78cb9864c10454010020001010c
INFO:root:hid rx: command=CBOR payload=04
INFO:root:ble tx: command=MSG payload=04
INFO:root:ble rx: command=KEEPALIVE payload=01
INFO:root:hid tx: command=KEEPALIVE payload=01
INFO:root:ble rx: command=MSG payload=00ad0182684649444f5f325f30684649444f5f325f3102826b686d61632d7365637265746b6372656450726f74656374035069700f79d1fb472ebd9ba3a3b9a9eda004a962726bf5627570f5627576f564706c6174f468616c776179735576f468637265644d676d74f569636c69656e7450696ef56e70696e557641757468546f6b656ef5706d616b654372656455764e6f74527164f50519040006820102098163626c650a82a263616c672664747970656a7075626c69632d6b6579a263616c6739010064747970656a7075626c69632d6b65790cf40d040e0111081203
INFO:root:hid tx: command=CBOR payload=00ad0182684649444f5f325f30684649444f5f325f3102826b686d61632d7365637265746b6372656450726f74656374035069700f79d1fb472ebd9ba3a3b9a9eda004a962726bf5627570f5627576f564706c6174f468616c776179735576f468637265644d676d74f569636c69656e7450696ef56e70696e557641757468546f6b656ef5706d616b654372656455764e6f74527164f50519040006820102098163626c650a82a263616c672664747970656a7075626c69632d6b6579a263616c6739010064747970656a7075626c69632d6b65790cf40d040e0111081203
INFO:root:hid rx: command=CBOR payload=04
INFO:root:ble tx: command=MSG payload=04
INFO:root:ble rx: command=MSG payload=00ad0182684649444f5f325f30684649444f5f325f3102826b686d61632d7365637265746b6372656450726f74656374035069700f79d1fb472ebd9ba3a3b9a9eda004a962726bf5627570f5627576f564706c6174f468616c776179735576f468637265644d676d74f569636c69656e7450696ef56e70696e557641757468546f6b656ef5706d616b654372656455764e6f74527164f50519040006820102098163626c650a82a263616c672664747970656a7075626c69632d6b6579a263616c6739010064747970656a7075626c69632d6b65790cf40d040e0111081203
INFO:root:hid tx: command=CBOR payload=00ad0182684649444f5f325f30684649444f5f325f3102826b686d61632d7365637265746b6372656450726f74656374035069700f79d1fb472ebd9ba3a3b9a9eda004a962726bf5627570f5627576f564706c6174f468616c776179735576f468637265644d676d74f569636c69656e7450696ef56e70696e557641757468546f6b656ef5706d616b654372656455764e6f74527164f50519040006820102098163626c650a82a263616c672664747970656a7075626c69632d6b6579a263616c6739010064747970656a7075626c69632d6b65790cf40d040e0111081203
INFO:root:hid rx: command=CBOR payload=06a201010201
INFO:root:ble tx: command=MSG payload=06a201010201
INFO:root:ble rx: command=MSG payload=00a10308
INFO:root:hid tx: command=CBOR payload=00a10308
INFO:root:hid rx: command=CBOR payload=06a201010207
INFO:root:ble tx: command=MSG payload=06a201010207
INFO:root:ble rx: command=MSG payload=00a10508
INFO:root:hid tx: command=CBOR payload=00a10508
INFO:root:hid rx: command=CBOR payload=40a201010207
INFO:root:ble tx: command=MSG payload=40a201010207
INFO:root:ble rx: command=MSG payload=01
INFO:root:hid tx: command=CBOR payload=01
```

It works perfectly fine with `fido2-token`, `fido2-cred`, and `fido2-assert`

In principle, this also works with the Chrome and Firefox. Give it a try!

My current (horribly outdated) firmware version still has some issues, probably related to not having my finger print properly enrolled when I try it out with Chrome and https://webauthn.io, however the forwarding of the HID and BLE packets looks fine. 

## Credit
`/dev/uhid` handling took a lot of notes from https://github.com/BryanJacobs/fido2-hid-bridge but was rewritten significantly.
