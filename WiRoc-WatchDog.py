#!/usr/bin/env python3
import subprocess
import time
import yaml
import gpiod
from smbus2 import SMBus
import logging, logging.handlers
import os
import os.path

# Configuration and settings
GreenNanoPiLEDPath = "/sys/class/leds/nanopi\\:blue\\:status/trigger"
GpioLedPinNo = 6
GpioLEDPath = f"/sys/class/gpio/gpio{GpioLedPinNo}/value"
GpioLEDExportPath = "/sys/class/gpio/export"
WARNING_INTERVAL = 0.5
NORMAL_INTERVAL = 2
TemperatureLevelWarning = 85.0
TemperatureLevelTooHighForCurrentChargingSpeed = 83.0
TemperatureLevelTooLowForCurrentChargingSpeed = 75.0
TemperatureLevelError = 90.0
BatteryLevelWarning: int = 9
BatteryLevelError: int = 7

# Constants
POWERMODE_CHARGING_REGADDR: int = 0x01
IRQ_STATUS_3_REGADDR: int = 0x4a
IRQ_STATUS_4_REGADDR: int = 0x4b
ADC_ENABLE_REGADDR: int = 0x82
POWER_MEASUREMENT_RESULT_REGADDR: int = 0xb9
PEK_KEY_SETTINGS_REGADDR: int = 0x36
GPIO2_FEATURE_SET_REGADDR: int = 0x93
CHARGE_CONTROL_1_REGADDR: int = 0x33
VBUSIPSOUT_POWER_PATH_MANAGEMENT_REGADDR: int = 0x30
IRQ_STATUS_3_REGADDR: int = 0x4a
I2CAddressAXP209: int = 0x34

CONTROL_STATUS_2_REGADDR: int = 0x01
MINUTE_ALARM_REGADDR: int = 0x09
HOUR_ALARM_REGADDR: int = 0x0a
DAY_ALARM_REGADDR: int = 0x0b
WEEKDAY_ALARM_REGADDR: int = 0xc
I2CAddressRTC: int = 0x51

# Global variables
StatusLEDStateOn: bool = False
CurrentInterval: int = NORMAL_INTERVAL
LEDPin = None
I2CBus = None
HardwareVersionAndRevision: str = None
HardwareVersion: int = None
Logger = None


class Samplings:
	SampleReadingsTime = time.monotonic()
	PreviousTemperature = 0
	CurrentTemperature = 0
	PreviousBatteryPercent = 100
	CurrentBatteryPercent = 100
	CurrentIsWiRocBLEAPIActive = True
	CurrentIsWiRocPythonActive = True
	CurrentIsWiRocPythonWSActive = True
	IsCharging = True

	@classmethod
	def GetPMUTemperature(cls):
		TEMPERATURE_MSB_REGADDR = 0x5e
		TEMPERATURE_LSB_REGADDR = 0x5f
		temperatureHighByte = I2CBus.read_byte_data(I2CAddressAXP209, TEMPERATURE_MSB_REGADDR)
		temperatureLowByte = I2CBus.read_byte_data(I2CAddressAXP209, TEMPERATURE_LSB_REGADDR)
		# PMU Internal temperature 000 is -144.7C steps of 0.1C, FFF is 264.8C
		temperatureCelsius = ((temperatureHighByte << 4 | (temperatureLowByte & 0xF)) - 1447) / 10
		return temperatureCelsius

	@classmethod
	def GetBatteryPercent(cls):
		intPercentValue = I2CBus.read_byte_data(I2CAddressAXP209, POWER_MEASUREMENT_RESULT_REGADDR)
		return intPercentValue

	@classmethod
	def GetBatteryIsCharging(cls):
		intValue = I2CBus.read_byte_data(I2CAddressAXP209, POWERMODE_CHARGING_REGADDR)
		isCharging = (intValue & 0x40) > 0
		return isCharging

	@classmethod
	def GetIsWiRocBLEAPIActive(cls):
		res = subprocess.run(['systemctl', 'is-active', 'WiRocBLEAPI.service'], check=False, capture_output=True).stdout
		return res == b"active\n"

	@classmethod
	def GetIsWiRocPythonActive(cls):
		res = subprocess.run(['systemctl', 'is-active', 'WiRocPython.service'], check=False, capture_output=True).stdout
		return res == b"active\n"

	@classmethod
	def GetIsWiRocPythonWSActive(cls):
		res = subprocess.run(['systemctl', 'is-active', 'WiRocPythonWS.service'], check=False, capture_output=True).stdout
		return res == b"active\n"

	@classmethod
	def SampleReadings(cls):
		elapsedTime = time.monotonic() - cls.SampleReadingsTime
		if elapsedTime > 10:
			cls.PreviousTemperature = cls.CurrentTemperature
			cls.CurrentTemperature = cls.GetPMUTemperature()
			cls.PreviousBatteryPercent = cls.CurrentBatteryPercent
			cls.CurrentBatteryPercent = cls.GetBatteryPercent()
			cls.IsCharging = cls.GetBatteryIsCharging()
			cls.CurrentIsWiRocBLEAPIActive = cls.GetIsWiRocBLEAPIActive()
			cls.CurrentIsWiRocPythonActive = cls.GetIsWiRocPythonActive()
			cls.CurrentIsWiRocPythonWSActive = cls.GetIsWiRocPythonWSActive()
			cls.SampleReadingsTime = time.monotonic()
			return True
		else:
			return False

	@classmethod
	def GetIsLongKeyPress(cls):
		statusReg = I2CBus.read_byte_data(I2CAddressAXP209, IRQ_STATUS_3_REGADDR)
		longKeyPress = statusReg & 0x01
		return longKeyPress > 0


class Evaluator():
	Logger = logging.getLogger("WatchDog")

	@classmethod
	def IsTemperatureWarning(cls):
		cls.Logger.debug(f"Temperature is: {Samplings.CurrentTemperature} C")
		if Samplings.CurrentTemperature > TemperatureLevelWarning:
			cls.Logger.warning(f"Temperature is above {TemperatureLevelWarning}C ({Samplings.CurrentTemperature}C) -- WARNING")
			return True
		return False

	@classmethod
	def IsBatteryWarning(cls):
		cls.Logger.debug(f"Battery is: {Samplings.CurrentBatteryPercent}% Battery charging: {Samplings.IsCharging}")
		# Battery percentage returned is inaccurate when charging
		if Samplings.IsCharging:
			return False
		if Samplings.CurrentBatteryPercent <= BatteryLevelWarning:
			cls.Logger.warning(f"Battery is below {BatteryLevelWarning}%  -- WARNING")
			return True
		return False

	@classmethod
	def IsWiRocBLEAPIActiveWarning(cls):
		if not Samplings.CurrentIsWiRocBLEAPIActive:
			cls.Logger.warning("WiRocBLEAPI NOT ACTIVE")
			return True
		return False

	@classmethod
	def IsIsWiRocPythonActiveWarning(cls):
		if not Samplings.CurrentIsWiRocPythonActive:
			cls.Logger.warning("WiRocPython NOT ACTIVE")
			return True
		return False

	@classmethod
	def IsWiRocPythonWSActiveWarning(cls):
		if not Samplings.CurrentIsWiRocPythonWSActive:
			cls.Logger.warning("WiRocPythonWS NOT ACTIVE")
			return True
		return False

	@classmethod
	def IsWarning(cls):
		return (cls.IsTemperatureWarning()
										or cls.IsBatteryWarning()
										or cls.IsWiRocBLEAPIActiveWarning()
										or cls.IsIsWiRocPythonActiveWarning()
										or cls.IsWiRocPythonWSActiveWarning())

	@classmethod
	def IsTemperatureError(cls):
		if Samplings.CurrentTemperature > TemperatureLevelError:
			cls.Logger.error(f"Temperature is above {TemperatureLevelError}C ({Samplings.CurrentTemperature}C)")
			if Samplings.PreviousTemperature > TemperatureLevelError:
				cls.Logger.error(f"Previous Temperature was also above {TemperatureLevelError}C ({Samplings.PreviousTemperature}C)")
				return True
		return False

	@classmethod
	def IsBatteryError(cls):
		cls.Logger.debug(f"Battery is: {Samplings.CurrentBatteryPercent}% Battery charging: {Samplings.IsCharging}")
		# Battery percentage returned is inaccurate when charging
		if Samplings.IsCharging:
			return False
		if Samplings.CurrentBatteryPercent < BatteryLevelError:
			cls.Logger.error(f"Battery is below {BatteryLevelError}% ({Samplings.CurrentBatteryPercent}%)")
			if Samplings.PreviousBatteryPercent < BatteryLevelError:
				cls.Logger.error(f"Previous Battery was also below {BatteryLevelError}% ({Samplings.PreviousBatteryPercent}%)")
				return True
		return False

	@classmethod
	def IsTemperatureLevelTooHighForCurrentCharging(cls):
		if Samplings.CurrentTemperature > TemperatureLevelTooHighForCurrentChargingSpeed:
			cls.Logger.debug(f"Temperature is above {TemperatureLevelTooHighForCurrentChargingSpeed}C ({Samplings.CurrentTemperature}C) (Should decrease charging speed)")
			return True
		return False

	@classmethod
	def IsTemperatureLevelTooLowForCurrentCharging(cls):
		if Samplings.CurrentTemperature < TemperatureLevelTooLowForCurrentChargingSpeed:
			cls.Logger.debug(f"Temperature is below {TemperatureLevelTooLowForCurrentChargingSpeed}C ({Samplings.CurrentTemperature}C) (OK to increase charging speed)")
			return True
		return False


def BlinkLED():
	global StatusLEDStateOn
	global HardwareVersionAndRevision
	global LEDPin

	if StatusLEDStateOn:
		subprocess.call(f"echo 'none' > {GreenNanoPiLEDPath}", shell=True)
		StatusLEDStateOn = False
	else:
		subprocess.call(f"echo 'default-on' > {GreenNanoPiLEDPath}", shell=True)
		StatusLEDStateOn = True


CHARGING_SPEEDS = {
	7: {"Name": "900", "RegValue": 0xC6},
	6: {"Name": "800", "RegValue": 0xC5},
	5: {"Name": "700", "RegValue": 0xC4},
	4: {"Name": "600", "RegValue": 0xC3},
	3: {"Name": "500", "RegValue": 0xC2},
	2: {"Name": "400", "RegValue": 0xC1},
	1: {"Name": "300", "RegValue": 0xC0},
	0: {"Name": "DISABLED", "RegValue": 0x40},
}


def IncreaseChargingSpeed(ChargingSpeed: int):
	if ChargingSpeed < 6:
		ChargingSpeed += 1
	return ChargingSpeed


def DecreaseChargingSpeed(ChargingSpeed: int):
	if ChargingSpeed > 0:
		ChargingSpeed -= 1
	return ChargingSpeed


def SetChargingSpeed(ChargeSpeed: int):
	Logger.info(f"Set charge speed: {CHARGING_SPEEDS[ChargeSpeed]['Name']} ({Samplings.CurrentTemperature}C)")
	I2CBus.write_byte_data(I2CAddressAXP209, CHARGE_CONTROL_1_REGADDR, CHARGING_SPEEDS[ChargeSpeed]["RegValue"])


def SetMaxPowerDrawUSB_NoLimit():
	Logger.info("Set power draw NO LIMIT")
	I2CBus.write_byte_data(I2CAddressAXP209, VBUSIPSOUT_POWER_PATH_MANAGEMENT_REGADDR, 0x63)


def SetMaxPowerDrawUSB_100():
	Logger.info("Set power draw 100 mA")
	I2CBus.write_byte_data(I2CAddressAXP209, VBUSIPSOUT_POWER_PATH_MANAGEMENT_REGADDR, 0x62)


def SetMaxPowerDrawUSB_500():
	Logger.info("Set power draw 500 mA")
	I2CBus.write_byte_data(I2CAddressAXP209, VBUSIPSOUT_POWER_PATH_MANAGEMENT_REGADDR, 0x61)


def SetMaxPowerDrawUSB_900():
	Logger.info("Set power draw 900 mA")
	I2CBus.write_byte_data(I2CAddressAXP209, VBUSIPSOUT_POWER_PATH_MANAGEMENT_REGADDR, 0x60)

def ConfigureRTCAlarm():
	# Check if we should configure the alarm, the Day_alarm register is set to 0x02 
	# (ie day 2 in the month, but with AE_D, "alarm enable day" cleared (disabled))
	dayAlarm: int = I2CBus.read_byte_data(I2CAddressRTC, DAY_ALARM_REGADDR, force=True)
	if dayAlarm == 0x02:
		Logger.info(f"Enable the wakeup alarm")
		# enable the minute part of the alarm
		minuteAlarm: int = I2CBus.read_byte_data(I2CAddressRTC, MINUTE_ALARM_REGADDR, force=True)
		minuteAlarm &= 0x7F
		I2CBus.write_byte_data(I2CAddressRTC, MINUTE_ALARM_REGADDR, minuteAlarm, force=True)
		# enable the hour part of the alarm
		hourAlarm: int = I2CBus.read_byte_data(I2CAddressRTC, HOUR_ALARM_REGADDR, force=True)
		hourAlarm &= 0x7F
		I2CBus.write_byte_data(I2CAddressRTC, HOUR_ALARM_REGADDR, hourAlarm, force=True)
		# Clear the day alarm and disable it
		I2CBus.write_byte_data(I2CAddressRTC, DAY_ALARM_REGADDR, 0x80, force=True)
		# Clear the week day alarm and disable it
		I2CBus.write_byte_data(I2CAddressRTC, WEEKDAY_ALARM_REGADDR, 0x80, force=True)
		# enable the "global" interrupt
		I2CBus.write_byte_data(I2CAddressRTC, CONTROL_STATUS_2_REGADDR, 0x02, force=True)


def Shutdown(reason: str):
	Logger.info(f"Shutdown: {reason}")

	# Set Status LED to ON
	global StatusLEDStateOn
	StatusLEDStateOn = False
	BlinkLED()
	
	global HardwareVersion
	if HardwareVersion >= 7:
		ConfigureRTCAlarm()
		
	# Sleep so that WiRocPython has time to write "shutting down" on the OLED first
	time.sleep(0.5)
	# set shutdown delay to 10 seconds
	I2CBus.write_byte_data(I2CAddressAXP209, PEK_KEY_SETTINGS_REGADDR, 0x9F)
	# Set gpio2 on axp209 to low, this will shutdown the axp209 after the shutdown delay (if gpio2 connected to power-on/off pin)
	# (this should maybe be run in separate process run later in the shutdown sequence)
	I2CBus.write_byte_data(I2CAddressAXP209, GPIO2_FEATURE_SET_REGADDR, 0x00)
	os.system('shutdown --poweroff now')


def Init():
	logging.basicConfig(level=logging.ERROR,
						format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
						filename='WatchDog.log',
						filemode='a')
	logging.raiseExceptions = False
	formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
	rotFileHandler = logging.handlers.RotatingFileHandler('WatchDog.log', maxBytes=20000000, backupCount=3)
	rotFileHandler.doRollover()
	rotFileHandler.setFormatter(formatter)

	# define a Handler which writes INFO messages or higher to the sys.stderr
	console = logging.StreamHandler()
	console.setLevel(logging.DEBUG)
	console.setFormatter(formatter)

	# add the handler to the myLogger
	global Logger
	Logger = logging.getLogger('WatchDog')
	Logger.setLevel(logging.INFO)
	Logger.propagate = False
	Logger.addHandler(rotFileHandler)
	Logger.addHandler(console)

	Logger.info("Start")

	global HardwareVersionAndRevision
	global HardwareVersion
	global UseGpioLED
	global LEDPin
	global I2CBus


	# HW Version
	f = open("/home/chip/settings.yaml", "r")
	settings = yaml.load(f, Loader=yaml.BaseLoader)
	f.close()
	HardwareVersionAndRevision = ""
	if "WiRocHWVersion" in settings:
		HardwareVersionAndRevision = settings["WiRocHWVersion"]
		HardwareVersionAndRevision = HardwareVersionAndRevision.strip()
		HardwareVersion = int(HardwareVersionAndRevision.split("Rev")[0][1:])
		Logger.info("Hardware Version And Revision: " + HardwareVersionAndRevision)

	chip = gpiod.chip('gpiochip0')
	if HardwareVersionAndRevision == "v3Rev2":
		Logger.info("Turn off the external LED (we use the LED on the nanopi)")

		chip = gpiod.chip('gpiochip0')
		configOutput = gpiod.line_request()
		configOutput.consumer = "wirocwatchdog"
		configOutput.request_type = gpiod.line_request.DIRECTION_OUTPUT

		LEDPin = chip.get_line(GpioLedPinNo)
		LEDPin.request(configOutput)
		LEDPin.set_value(1)


	# Init battery
	# force ADC enable for battery voltage and current
	#i2cset -y -f 0 0x34 0x82 0xC3
	I2CBus = SMBus(0)  # 0 = /dev/i2c-0 (port I2C0), 1 = /dev/i2c-1 (port I2C1)
	I2CBus.write_byte_data(I2CAddressAXP209, ADC_ENABLE_REGADDR, 0xC3)

	SetMaxPowerDrawUSB_NoLimit()


def main():
	filePathPMUIRQ: str = '/home/chip/PMUIRQ.txt'
	global CurrentInterval
	Init()
	CurrentChargingSpeed = 4
	PreviousChargingSpeed = 0
	while True:
		time.sleep(CurrentInterval)
		BlinkLED()

		if Samplings.SampleReadings():
			# new samples
			if Evaluator.IsWarning():
				CurrentInterval = WARNING_INTERVAL
			else:
				CurrentInterval = NORMAL_INTERVAL

			if Evaluator.IsTemperatureLevelTooHighForCurrentCharging():
				CurrentChargingSpeed = DecreaseChargingSpeed(CurrentChargingSpeed)
			if Evaluator.IsTemperatureLevelTooLowForCurrentCharging():
				CurrentChargingSpeed = IncreaseChargingSpeed(CurrentChargingSpeed)

			if PreviousChargingSpeed != CurrentChargingSpeed:
				SetChargingSpeed(CurrentChargingSpeed)
				PreviousChargingSpeed = CurrentChargingSpeed

			if Evaluator.IsTemperatureError():
				Shutdown(f"Temperature error: {Samplings.CurrentTemperature} C")

			if Evaluator.IsBatteryError():
				Shutdown(f"Battery error: {Samplings.CurrentBatteryPercent}%")

		if os.path.exists(filePathPMUIRQ):
			os.remove(filePathPMUIRQ)
			if Samplings.GetIsLongKeyPress():
				Shutdown("User did a Long key press")


if __name__ == '__main__':
	main()
