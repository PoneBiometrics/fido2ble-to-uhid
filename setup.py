from setuptools import setup, find_packages

setup(name='fido2ble',
      version='0.0.1',
      description='',
      author='Jó Ágila Bitsch',
      author_email='jo.bitsch@gmail.com',
      url='https://github.com/PoneBiometrics/fido2ble/',
      packages=find_packages(),
      entry_points={
          'console_scripts': [
              'fido2ble=fido2ble.fido2ble:main'
          ]
      }
     )
