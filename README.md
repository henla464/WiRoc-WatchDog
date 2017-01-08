# WiRoc-Monitor

This is based on the blink program and is forked from https://github.com/fordsfords/blink/tree/gh-pages

## License

I want there to be NO barriers to using this code, so I am releasing it to the public domain.  But "public domain" does not have an internationally agreed upon definition, so I use CC0:


Copyright 2017 Henrik Larsson and licensed
"public domain" style under
[CC0](http://creativecommons.org/publicdomain/zero/1.0/): 
![CC0](https://licensebuttons.net/p/zero/1.0/88x31.png "CC0")

To the extent possible under law, the contributors to this project have
waived all copyright and related or neighboring rights to this work.
In other words, you can use this code for any purpose without any
restrictions. 

# Some documentions below kept from blink but not updated

## Quick Start

These instructions assume you are in a shell prompt on CHIP.

1. Prerequisites.  If you plan on blinking CHIP's status LED, and/or monitoring the reset button and/or battery, you will need the "i2c-tools" package, installable like this:

        sudo apt-get install i2c-tools

    If you plan to use GPIO inputs and/or outputs, you will need "gpio_sh" package, installable like this:

        sudo wget -O /usr/local/bin/gpio.sh https://raw.githubusercontent.com/henla464/WiRoc-Monitor/master/gpio.sh
    (See https://github.com/fordsfords/gpio_sh/tree/gh-pages for details of "gpio_sh".)

2. If you have an earlier version of blink running, kill it:

        sudo service blink stop

    If that returns a failure, enter:

        sudo kill `cat /tmp/blink.pid`

3. Get the project files onto CHIP:

        sudo wget -O /usr/local/bin/blink.sh https://raw.githubusercontent.com/henla464/WiRoc-Monitor/master/blink.sh
        sudo chmod +x /usr/local/bin/blink.sh
        sudo wget -O /etc/systemd/system/blink.service https://raw.githubusercontent.com/henla464/WiRoc-Monitor/master/blink.service
        sudo systemctl enable /etc/systemd/system/blink.service

    If installing blink for the first time, get the configuration file:

        sudo wget -O /usr/local/etc/blink.cfg https://raw.githubusercontent.com/henla464/WiRoc-Monitor/master/blink.cfg

    If upgrading blink and have a configuration file, you can skip that step.

4. Now test it:

        sudo service blink start

5. After a few seconds watching the blinking LED, briefly press the reset button and watch CHIP shut down.  Restart CHIP, and when it has completed its reboot, watch the status LED start to blink again.

6. Check logging:

        grep blink /var/log/syslog


## Details

Blink can monitor up to 4 conditions in any combination:
* Short press of reset button.
* A configured GPIO input reading a configured value (e.g. an external button).
* The AXP209 temperature exceeding a configured threshold.
* The battery charge level dropping below a configured threshold (only applies if CHIP is running only on battery; an external power source will suppress battery monitoring).

While blink is running, it can be configured to blink either CHIP's status LED,
or an external LED connected to a GPIO output (or both).

For temperature and battery monitoring, here are actually two configurable thresholds available: a warning threshold and a shutdown threshold.  There is also a configurable warning GPIO output.  For example, the temperature warning GPIO could turn on a fan, and the battery warning GPIO could be used to enter a reduced power mode by removing power to a non-critical external device.

Note that if blink shuts CHIP down due to low battery, it will not be possible to boot CHIP successfully without connecting to a power supply.  If you try, blink will immediately detect low battery and will shut down before the system is fully booted.  Similarly, if blink shuts CHIP down due to high temperature, you must let CHIP cool before you can boot it.
## Killing Blink

Since blink is a service, you can manually stop it with:

        sudo service blink stop


## Configuring Blink

Edit the file /usr/local/etc/blink.cfg it should look like this:

        # blink.cfg -- version 24-Jul-2016
        # Configuration for /usr/local/bin/blink.sh which is normally
        # installed as a service started at bootup.
        # See https://github.com/fordsfords/blink/tree/gh-pages

        BLINK_STATUS=1       # Blink CHIP's status LED.
        #BLINK_GPIO=XIO_P7    # Blink a GPIO.

        MON_RESET=1          # Monitor reset button for short press.
        #MON_GPIO=XIO_P4      # Shutdown when this GPIO is triggered.
        #MON_GPIO_VALUE=0     # The value read from MON_GPIO that initiates shutdown.

        #MON_BATTERY=7        # When battery percentage is below this, shut down.
        #WARN_BATTERY=9       # When battery percentage is below this, assert warning.
        #WARN_BATTERY_GPIO=XIO_P5  # When battery warning, activate this GPIO.
        #WARN_BATTERY_GPIO_VALUE=0 # Warning value to write to WARN_BATTERY_GPIO.

        #MON_TEMPERATURE=800  # Shutdown temperature in tenths of a degree C. 
        #WARN_TEMPERATURE=750 # Warning temperature in tenths of a degree C. 
        #WARN_TEMPERATURE_GPIO=XIO_P6  # When temperature warning, activate this GPIO.
        #WARN_TEMPERATURE_GPIO_VALUE=0 # Warning value to write to
        #WARN_TEMPERATURE_GPIO.

The hash sign (#) represents a comment.  Most lines are commented, so their functions do not apply.  I.e. the above (default) configuration only blinks CHIP's status LED and only monitors the reset button for short press.  You can enable a function by uncommenting it (remove the hash signs).  Or you can comment lines (add the hash) to disable a function.

Do not add any spaces before or after the equals sign.

For example, to skip all blinking of LEDs, and only monitor the battery,
writing "1" to GPIO CSID0 when the battery drops below 10%, and shutting down
when the battery drops below 5%:

        #BLINK_STATUS=1       # Blink CHIP's status LED.
        #BLINK_GPIO=XIO_P7    # Blink a GPIO.

        #MON_RESET=1          # Monitor reset button for short press.
        #MON_GPIO=XIO_P4      # Shutdown when this GPIO is triggered.
        #MON_GPIO_VALUE=0     # The value read from MON_GPIO that initiates shutdown.

        MON_BATTERY=5         # When battery percentage is below this, shut down.
        WARN_BATTERY=10       # When battery percentage is below this, assert warning.
        WARN_BATTERY_GPIO=CSID0   # When battery warning, activate this GPIO.
        WARN_BATTERY_GPIO_VALUE=1 # Warning value to write to WARN_BATTERY_GPIO.

        #MON_TEMPERATURE=800  # Shutdown temperature in tenths of a degree C. 
        #WARN_TEMPERATURE=750 # Warning temperature in tenths of a degree C. 
        #WARN_TEMPERATURE_GPIO=XIO_P6  # When temperature warning, activate this GPIO.
        #WARN_TEMPERATURE_GPIO_VALUE=0 # Warning value to write to
        #WARN_TEMPERATURE_GPIO.

## Random Notes

1. Blink logs informational (and maybe error) messages to /var/log/daemon.log

