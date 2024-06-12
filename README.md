# fido2ble-to-uhid
Bridging FIDO2 BLE devices to the HID bus via /dev/uhid so they can be used in browsers


## Dependencies on debian-based systems

For development on the python code you need to run 
```
pip install uhid dbus-fast
```

## Running it

Run the following command in a new shell:

```
fido2ble_to_uhid/fido2ble_to_uhid.py
```
The above needs some elevated privileges, either through running as root, sudo or by granting python the capabilities needed.

## As a debian package

The code can also be built as a debian package and installed that way. It requires a minimum of Debian Bullseye (11) or Ubuntu Manic Minotaur (23) to build and install. 
Running `debuild` in the base folder will create the needed files. 

## Verifying that it runs
The system can be verified to work through either [libfido2](https://github.com/Yubico/libfido2) or just testing it in a browser. Below is an example of how this would be done 
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

### Pairing

The easiest way to pair a new OFFPAD is through a terminal with bluetoothctl

Turning on scanning can be done through 

```
bluetoothctl scan on
```

This will then list all devices found as they get found and will run in the foreground. The job can be either backgrounded or the rest of the commands run in a new terminal.

Devices can then be listed with `bluetoothctl devices` which will display all found devices. To easily pair the OFFPAD running

```
bluetoothctl devices | grep OFFPAD
```

Will list any OFFPADs found. The OFFPAD will show as something like

```
Device 12:34:56:78:9A:BC OFFPAD
```

It is important to note the MAC address here as by doing 

```
bluetoothctl pair 12:34:56:78:9A:BC
```

The OFFPAD will prompt for a pairing code and after that the OFFPAD is paired. We can then turn of the scan that we either sent to the background or have in a different tab. If we backgrounded it, running `fg` will bring it to the foreground before we terminate it with `CTRL+C`

### Notes

It currently only works, if the OFFPAD is previously paired. The code is also set to find OFFPADs as FIDO devices only. If any changes happen to pairings, either new pairing or a removal, the python application must be restarted to updates the UHID devices available.  



## Credit
`/dev/uhid` handling took a lot of notes from https://github.com/BryanJacobs/fido2-hid-bridge but was rewritten significantly.
