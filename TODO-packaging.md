# Target distributions
* ubuntu LTS 22.04 + 24.04
* debian bullseye and bookworm

docker run -ti  --volume .:/tmp/fido2ble-to-uhid ubuntu:manic
apt-get update
apt-get install -y devscripts dh-sequence-python3 python3-setuptools python3-all debhelper-compat pybuild-plugin-pyproject
cd /tmp/fido2ble-to-uhid
debuild


## Bullseye
docker run -ti  --volume .:/tmp/fido2ble-to-uhid debian:bullseye
apt-get update
apt install --no-install-recommends devscripts
apt install --no-install-recommends dh-sequence-python3 debhelper-compat build-essential python3-setuptools
