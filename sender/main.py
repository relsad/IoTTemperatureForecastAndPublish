from time import ticks_ms, ticks_us, ticks_diff, sleep, sleep_us, sleep_ms
from machine import SoftI2C, Pin, deepsleep
from sx1262 import SX1262
from struct import pack, unpack
from ubinascii import crc32, hexlify
from math import ceil
from uhashlib import sha256
import _thread
import ssd1306
import network
import random
import onewire, ds18x20,machine
import max44009

# lightsensor
i2c = machine.I2C(scl=Pin(46), sda=Pin(45))
print('Scan i2c bus...')
devices = i2c.scan()
print(devices)

# SPI pins
CS   = 8
SCK  = 9
MOSI = 10
MISO = 11
RST  = 12
BUSY = 13
RX   = 14


def lora_send(msg):
    lora = SX1262(1, SCK, MOSI, MISO, CS, RX, RST, BUSY)

    MY_ID = 0x0B # to be filled in get_id (1 byte, so up to 256 devices)
    my_mac = " "
    DevAddr = ""
    # get_id()

    (my_sf, my_bw_plain) = (0x07, 125)
    freqs = [868.1, 868.3, 868.5, 867.1, 867.3, 867.5, 867.7, 867.9, 869.525]
    lora.begin(freq=freqs[0], bw=125.0, sf=7, cr=5, blocking=True)
    lora.send(msg)
        
def get_temp():
    ds_pin=machine.Pin(48)
    ds_sensor=ds18x20.DS18X20(
        onewire.OneWire(ds_pin))
    roms=ds_sensor.scan()
    ds_sensor.convert_temp()
    for rom in roms:
        temp=ds_sensor.read_temp(rom)
    return temp

def illuminance_lux(i2c, l):
    data = i2c.readfrom_mem(l, 0x03, 2)   # Register lux high byte
    exponent = (data[0] & 0xF0) >> 4
    mantissa = ((data[0] & 0x0F) << 4) | (data[1] & 0x0F)
    illuminance = (2**exponent)*mantissa*0.045
    return illuminance   # float in lux

def compare_temperature(temp):
    # Initialize RTC
    rtc = machine.RTC()
    # Read previous data from RTC memory
    try:
        data = eval(rtc.memory())
        previous_temp, count = data[0], data[1]
    except (SyntaxError, ValueError, TypeError):
        previous_temp = -100.0
        count = 0
    # Compare temperature and decide whether to wake up or not
    current_temp = temp
    print(f"previous temperature: {previous_temp}, count: {count}")
    if abs(current_temp - previous_temp )>= 0.5 or count > 5:
        toSend = 1 
        count = 0
        previous_temp = current_temp
    else:
        toSend += 1
        ret = 0
    data = [previous_temp, count]
    rtc.memory(str(data))
    return toSend
    
def get_data():
    l = i2c.scan()
    lum = illuminance_lux(i2c,l[0])
    temp = get_temp()
    if temp < -100:
        print("temp < -100, sensor error")
        return None
    res = compare_temperature(temp)
    if res == 0:
        print("not significant temp diff")
        return None, lum
    elif res == 1:
        return temp, lum
       
tmp, lum = get_data()
# if conditions are met
if tmp != None:
    pkt = pack('!ff',round(tmp,2),round(lum,2))
    print(f"sending packet: {pkt} with temperature {tmp} and luminosity {lum}")
    lora_send(pkt)
else:
    print("error data acquisition")
deepsleep(3600000) #deepsleep for 1 hour