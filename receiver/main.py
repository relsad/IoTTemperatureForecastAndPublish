import network, socket
from machine import Pin, SoftI2C
from machine import deepsleep
import machine
import ssd1306
import urequests as requests
import ujson
from time import ticks_ms, ticks_us, ticks_diff, sleep, sleep_us, sleep_ms
from sx1262 import SX1262
from struct import pack, unpack
from ubinascii import crc32, hexlify
from math import ceil
from uhashlib import sha256
import _thread
import random


# WiFi network
WIFI_SSID= ""# Network SSID
WIFI_PASS= ""# Network key
url = 'https://api.openai.com/v1/chat/completions'

led = Pin(35, Pin.OUT) # v3
rst = Pin(21, Pin.OUT)
rst.value(1)


OUT_API_KEY = "" #openweathermap API key
lat = "51.091737"
lon = "71.399037"

# Initialize the Wi-Fi interface
wlan = network.WLAN(network.STA_IF)
wlan.active(True)

# Connect to Wi-Fi
if not wlan.isconnected():
    wlan.connect(WIFI_SSID, WIFI_PASS)
    
    while not wlan.isconnected():
        machine.idle()  # Save power while waiting

print('Connected to WiFi\nIP Address: ' + wlan.ifconfig()[0])

# Telegram Bot credentials
BOT_TOKEN = "" #Telegram Bot Token
CHAT_ID = '' # Telegram channel ID
TELEGRAM_URL = "https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# SPI pins
SCK  = 9
MOSI = 10
MISO = 11
CS   = 8
RX   = 14
RST  = 12
BUSY = 13

lora = SX1262(1, SCK, MOSI, MISO, CS, RX, RST, BUSY)
(my_sf, my_bw_plain) = (0x07, 125)
freqs = [868.1, 868.3, 868.5, 867.1, 867.3, 867.5, 867.7, 867.9, 869.525]
lora.begin(freq=freqs[0], bw=125.0, sf=7, cr=5, blocking=True)

MY_ID = 0x0B # to be filled in get_id (1 byte, so up to 256 devices)
my_mac = ""
DevAddr = ""


# Change the "api_key" to your own
# Change the "open_ai_question" to what you want to ask

gpt_count = 1 # variable for def askGpt
prev_temp_in = None
prev_temp_out = None

def askGpt(temp, temp2, lum):
    global gpt_count, prev_temp_in, prev_temp_out
    if prev_temp_in:
        if gpt_count < 6 and (abs(prev_temp_in - temp) < 2.5 or abs(prev_temp_out - temp2)):
            gpt_count += 1
            return
    # when making chat gpt requests we would like to reset the counter and store the previous temp as current one 
    prev_temp_in = temp
    prev_temp_out = temp2
    gpt_count = 0

    questions = [f"Given temperature {temp} degrees C and luminosity {lum} lux in the University, will it be comfortable to work there right now? give brief recommendation of how to dress.",
                 f"Given temperature {temp} degrees C and luminosity {lum} lux in the University, will it be comfortable to use it as a collaboration space for event? give brief recommendation of how to dress.",
                 f"Given temperature {temp} degrees C and luminosity {lum} lux in the University, will it be comfortable to work with/without laptop there right now? give brief recommendation of how to dress.",
                 f"Given temperature {temp} degrees C and luminosity {lum} lux in the University, how would you recommend to dress for a lecture/group study session? give a brief response.",
                 f"Given temperature {temp} degrees C and luminosity {lum} lux in the University, what clothes combination you recommend for study/work, answer briefly why",]
    # Constraints
    open_ai_question = random.choice(questions) 
    telegram_question = "Comfortability to work in atrium"
    max_words = " Max 250 characters" 
    api_key = '' # ChatGPT API key

    payload = ujson.dumps({
    "model": "gpt-3.5-turbo-1106",
    "messages": [
        {
        "role": "user",
        "content": open_ai_question + max_words
        },
    ],
    "temperature": 1,
    "top_p": 1,
    "n": 1,
    "stream": False,
    "max_tokens": 150,
    "presence_penalty": 0,
    "frequency_penalty": 0
    })

    headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Authorization': 'Bearer ' + api_key
    }
    
    print("ask question, ", prev_temp_in, prev_temp_out, gpt_count)
    print(open_ai_question)
    
    # Post Data
    response = requests.post(url, headers=headers, data=payload)
    response_data = response.json()

    # Access JSON object
    open_ai_message = response_data["choices"][0]["message"]["content"]

    # Close the connection
    response.close()

    #print(open_ai_message)
    #print("\n")
    full_message = f"{telegram_question} according to ChatGPT\n\nResponse: {open_ai_message}"
    #print(full_message)
    #sendTelegramMessage(full_message)

def getOutTemp():
    resp = requests.get(
        f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OUT_API_KEY}")
    parsed_data = ujson.loads(resp.text)
    weather_main = parsed_data["weather"][0]["main"]
    temp = parsed_data["main"]["temp"]
    pressure = parsed_data["main"]["pressure"]
    humidity = parsed_data["main"]["humidity"]
    visibility = parsed_data["visibility"]
    wind_speed = parsed_data["wind"]["speed"]
    clouds_all = parsed_data["clouds"]["all"]
    weather_info = (
        f"Weather: {weather_main}\n",
        f"Temperature: {round(temp - 273.15, 2)} °C\n",
        f"Pressure: {pressure} hPa\n",
        f"Humidity: {humidity} %\n",
        f"Visibility: {visibility} meters\n",
        f"Wind Speed: {wind_speed} m/s\n",
        f"Cloudiness: {clouds_all} %\n"
    )
    return round(temp - 273.15, 2) if temp is not None else None

def sendTelegramMessage(message):
    url = TELEGRAM_URL
    data = {
        "chat_id": '', #chat id for telegram bot channel
        "text": message
    }
    # Send the POST request
    print(data)
    sleep(1)
    response = requests.post(url, json=data)

    # Check the response
    print(response.text)
    
def getTimeNow():
    time = requests.get(f"http://worldtimeapi.org/api/timezone/Asia/Tashkent")
    timedate = time.json()
    tim = timedate["datetime"]
    # Split datetime string into date and time
    date_str, time_str = tim.split("T")
    
    # Extract timezone offset
    time_str, time_zone_offset = time_str.split("+")
    return [date_str,time_str,time_zone_offset]

def outsideForecastApiTempCall(time_of_day):
    date_str,time_str,time_zone_offset = getTimeNow()
    API_KEY = "" #openweathermap API key
    lat = "51.091737"
    lon = "71.399037"
    units = "metric"
    cnt = "12"
    response = requests.get(f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={API_KEY}&units={units}&cnt={cnt}")
    if response.status_code == 200:
        # Process the response data
        json_data = response.json()
        #print(json_data)
        for cnt in json_data["list"]:
            forecast_date, forecast_time = cnt["dt_txt"].split(" ")
            if forecast_date != date_str and forecast_time == time_of_day:
                print(cnt["main"]["temp"])
                return cnt["main"]["temp"]
    else:
        print("Error:", response.status_code)

def predict(input):
    return 23.623651960784315 + input[0] * 0.2118175441859958 + input[1] * 0.5489272956132957


def scaleData(data):
    scaler_mean = [5.93181863, 12.78480392]
    scaler_std = [6.0335678 , 6.47909644]
    return [(x - mean) / std for x, mean, std in zip(data, scaler_mean, scaler_std)]
    
def postPredictTomorrowTemp():
    morning_out = outsideForecastApiTempCall("09:00:00")
    afternoon_out = outsideForecastApiTempCall("15:00:00")
    morning_pred = round(predict(scaleData([morning_out, 9])),2)
    afternoon_pred = round(predict(scaleData([afternoon_out, 15])),2)
    print("I'm a cat")
    message = f"Forecast for morning and afternoon:\nAtrium:    {morning_pred} C   {afternoon_pred} C\nOutside: {morning_out} C   {afternoon_out} C"
    sendTelegramMessage(message)

# while True:
#     try:
#         print("attempt at receiving...")
#         lora_data = lora.recv()
#         if lora_data:
#             print(lora_data)
#             msg = unpack('!ff', lora_data[0])
#             temp, lum = msg[0], msg[1]
#             temp_out = getOutTemp()
#             tel_msg = f"Atrium: {temp} ºC, {lum} lux"
#             tel_msg2 = f"Outside NU: {temp_out} ºC"
#             sleep(1)
#             print("sending message")
#             sendTelegramMessage(tel_msg)
#             sleep(1)
#             sendTelegramMessage(tel_msg2)
#             sleep(1)
#             askGpt(temp, temp_out, lum)
#             lora_data = None
#             
#     
#     except Exception as e:
#         print("Error happened", e)
postPredictTommorowTemp()
