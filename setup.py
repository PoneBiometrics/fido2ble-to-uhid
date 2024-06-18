from setuptools import setup, find_packages

setup(name='fido2ble-to-uhid',
      version='0.0.1',
      description='',
      author='Jó Ágila Bitsch',
      author_email='jo.bitsch@gmail.com',
      url='https://github.com/PoneBiometrics/fido2ble-to-uhid/',
      packages=find_packages(),
      entry_points={
          'console_scripts': [
              'fido2ble-to-uhid=fido2ble_to_uhid.fido2ble_to_uhid:main'
          ]
      }
     )