#!/usr/bin/env python3.7
import os
import json
import copy
import datetime
import psutil
from smbus2 import SMBus
from cereal import log
from common.basedir import BASEDIR
from common.params import Params
from common.realtime import sec_since_boot, DT_TRML
from common.numpy_fast import clip, interp
from common.filter_simple import FirstOrderFilter
from selfdrive.version import terms_version, training_version
from selfdrive.swaglog import cloudlog
import cereal.messaging as messaging
from selfdrive.loggerd.config import get_available_percent
from selfdrive.kegman_conf import KegmanConf

kegman = KegmanConf()
from selfdrive.pandad import get_expected_version

FW_VERSION = get_expected_version()

ThermalStatus = log.ThermalData.ThermalStatus
CURRENT_TAU = 15.   # 15s time constant
DAYS_NO_CONNECTIVITY_MAX = 7  # do not allow to engage after a week without internet
DAYS_NO_CONNECTIVITY_PROMPT = 4  # send an offroad prompt after 4 days with no internet


with open(BASEDIR + "/selfdrive/controls/lib/alerts_offroad.json") as json_file:
  OFFROAD_ALERTS = json.load(json_file)

def read_tz(x, clip=True):
  with open("/sys/devices/virtual/thermal/thermal_zone%d/temp" % x) as f:
    ret = int(f.read())
    if clip:
      ret = max(0, ret)

  return ret

def read_thermal():
  dat = messaging.new_message()
  dat.init('thermal')
  dat.thermal.cpu0 = read_tz(5)
  dat.thermal.cpu1 = read_tz(7)
  dat.thermal.cpu2 = read_tz(10)
  dat.thermal.cpu3 = read_tz(12)
  dat.thermal.mem = read_tz(2)
  dat.thermal.gpu = read_tz(16)
  dat.thermal.bat = read_tz(29)
  dat.thermal.pa0 = read_tz(25)
  return dat

LEON = False
def setup_eon_fan():
  global LEON

  os.system("echo 2 > /sys/module/dwc3_msm/parameters/otg_switch")

  bus = SMBus(7, force=True)
  try:
    bus.write_byte_data(0x21, 0x10, 0xf)   # mask all interrupts
    bus.write_byte_data(0x21, 0x03, 0x1)   # set drive current and global interrupt disable
    bus.write_byte_data(0x21, 0x02, 0x2)   # needed?
    bus.write_byte_data(0x21, 0x04, 0x4)   # manual override source
  except IOError:
    print("LEON detected")
    #os.system("echo 1 > /sys/devices/soc/6a00000.ssusb/power_supply/usb/usb_otg")
    LEON = True
  bus.close()

last_eon_fan_val = None
def set_eon_fan(val):
  global LEON, last_eon_fan_val

  if last_eon_fan_val is None or last_eon_fan_val != val:
    bus = SMBus(7, force=True)
    if LEON:
      try:
        i = [0x1, 0x3 | 0, 0x3 | 0x08, 0x3 | 0x10][val]
        bus.write_i2c_block_data(0x3d, 0, [i])
      except IOError:
        # tusb320
        if val == 0:
          bus.write_i2c_block_data(0x67, 0xa, [0])
          #bus.write_i2c_block_data(0x67, 0x45, [1<<2])
        else:
          #bus.write_i2c_block_data(0x67, 0x45, [0])
          bus.write_i2c_block_data(0x67, 0xa, [0x20])
          bus.write_i2c_block_data(0x67, 0x8, [(val-1)<<6])
    else:
      bus.write_byte_data(0x21, 0x04, 0x2)
      bus.write_byte_data(0x21, 0x03, (val*2)+1)
      bus.write_byte_data(0x21, 0x04, 0x4)
    bus.close()
    last_eon_fan_val = val

# temp thresholds to control fan speed - high hysteresis
_TEMP_THRS_H = [50., 65., 80., 10000]
# temp thresholds to control fan speed - low hysteresis
_TEMP_THRS_L = [42.5, 57.5, 72.5, 10000]
# fan speed options
_FAN_SPEEDS = [0, 16384, 32768, 65535]
# max fan speed only allowed if battery is hot
_BAT_TEMP_THERSHOLD = 45.


def handle_fan_eon(max_cpu_temp, bat_temp, fan_speed):
  new_speed_h = next(speed for speed, temp_h in zip(_FAN_SPEEDS, _TEMP_THRS_H) if temp_h > max_cpu_temp)
  new_speed_l = next(speed for speed, temp_l in zip(_FAN_SPEEDS, _TEMP_THRS_L) if temp_l > max_cpu_temp)

  if new_speed_h > fan_speed:
    # update speed if using the high thresholds results in fan speed increment
    fan_speed = new_speed_h
  elif new_speed_l < fan_speed:
    # update speed if using the low thresholds results in fan speed decrement
    fan_speed = new_speed_l

  if bat_temp < _BAT_TEMP_THERSHOLD:
    # no max fan speed unless battery is hot
    fan_speed = min(fan_speed, _FAN_SPEEDS[-2])

  set_eon_fan(fan_speed//16384)

  return fan_speed

def handle_fan_uno(max_cpu_temp, bat_temp, fan_speed):
  # TODO: implement better fan control
  return int(interp(max_cpu_temp, [40.0, 80.0], [0, 100]))

def check_car_battery_voltage(should_start, health, charging_disabled, msg):

  # charging disallowed if:
  #   - there are health packets from panda, and;
  #   - 12V battery voltage is too low, and;
  #   - onroad isn't started
  print(health)
  
  if charging_disabled and (health is None or health.health.voltage > (int(kegman.conf['carVoltageMinEonShutdown'])+500)) and msg.thermal.batteryPercent < int(kegman.conf['battChargeMin']):
    charging_disabled = False
    os.system('echo "1" > /sys/class/power_supply/battery/charging_enabled')
  elif not charging_disabled and (msg.thermal.batteryPercent > int(kegman.conf['battChargeMax']) or (health is not None and health.health.voltage < int(kegman.conf['carVoltageMinEonShutdown']) and not should_start)):
    charging_disabled = True
    os.system('echo "0" > /sys/class/power_supply/battery/charging_enabled')
  elif msg.thermal.batteryCurrent < 0 and msg.thermal.batteryPercent > int(kegman.conf['battChargeMax']):
    charging_disabled = True
    os.system('echo "0" > /sys/class/power_supply/battery/charging_enabled')

  return charging_disabled


def thermald_thread():
  # prevent LEECO from undervoltage
  BATT_PERC_OFF = int(kegman.conf['battPercOff'])
  
  health_timeout = int(1000 * 2.5 * DT_TRML)  # 2.5x the expected health frequency

  # now loop
  thermal_sock = messaging.pub_sock('thermal')
  health_sock = messaging.sub_sock('health', timeout=health_timeout)
  location_sock = messaging.sub_sock('gpsLocation')

  fan_speed = 0
  count = 0

  off_ts = None
  started_ts = None
  started_seen = False
  thermal_status = ThermalStatus.green
  thermal_status_prev = ThermalStatus.green
  usb_power = True
  usb_power_prev = True

  current_filter = FirstOrderFilter(0., CURRENT_TAU, DT_TRML)
  health_prev = None
  fw_version_match_prev = True
  current_connectivity_alert = None
  charging_disabled = False
  time_valid_prev = True
  should_start_prev = False

  is_uno = (read_tz(29, clip=False) < -1000)
  if is_uno:
    handle_fan = handle_fan_uno
  else:
    setup_eon_fan()
    handle_fan = handle_fan_eon

  params = Params()

  while 1:
    health = messaging.recv_sock(health_sock, wait=True)
    location = messaging.recv_sock(location_sock)
    location = location.gpsLocation if location else None
    msg = read_thermal()

    # clear car params when panda gets disconnected
    if health is None and health_prev is not None:
      params.panda_disconnect()
    health_prev = health

    if health is not None:
      usb_power = health.health.usbPowerMode != log.HealthData.UsbPowerMode.client

    msg.thermal.freeSpace = get_available_percent() / 100.0  # disk space
    msg.thermal.memUsedPercent = int(round(psutil.virtual_memory().percent))
    msg.thermal.cpuPerc = int(round(psutil.cpu_percent()))

    with open("/sys/class/power_supply/battery/capacity") as f:
      msg.thermal.batteryPercent = int(f.read())
    with open("/sys/class/power_supply/battery/status") as f:
      msg.thermal.batteryStatus = f.read().strip()
    with open("/sys/class/power_supply/battery/current_now") as f:
      msg.thermal.batteryCurrent = int(f.read())
    with open("/sys/class/power_supply/battery/voltage_now") as f:
      msg.thermal.batteryVoltage = int(f.read())
    with open("/sys/class/power_supply/usb/present") as f:
      msg.thermal.usbOnline = bool(int(f.read()))

    current_filter.update(msg.thermal.batteryCurrent / 1e6)

    # TODO: add car battery voltage check
    max_cpu_temp = max(msg.thermal.cpu0, msg.thermal.cpu1,
                       msg.thermal.cpu2, msg.thermal.cpu3) / 10.0
    max_comp_temp = max(max_cpu_temp, msg.thermal.mem / 10., msg.thermal.gpu / 10.)
    bat_temp = msg.thermal.bat/1000.

    fan_speed = handle_fan(max_cpu_temp, bat_temp, fan_speed)
    msg.thermal.fanSpeed = fan_speed

    # thermal logic with hysterisis
    if max_cpu_temp > 107. or bat_temp >= 63.:
      # onroad not allowed
      thermal_status = ThermalStatus.danger
    elif max_comp_temp > 92.5 or bat_temp > 60.: # CPU throttling starts around ~90C
      # hysteresis between onroad not allowed and engage not allowed
      thermal_status = clip(thermal_status, ThermalStatus.red, ThermalStatus.danger)
    elif max_cpu_temp > 87.5:
      # hysteresis between engage not allowed and uploader not allowed
      thermal_status = clip(thermal_status, ThermalStatus.yellow, ThermalStatus.red)
    elif max_cpu_temp > 80.0:
      # uploader not allowed
      thermal_status = ThermalStatus.yellow
    elif max_cpu_temp > 75.0:
      # hysteresis between uploader not allowed and all good
      thermal_status = clip(thermal_status, ThermalStatus.green, ThermalStatus.yellow)
    else:
      # all good
      thermal_status = ThermalStatus.green

    # **** starting logic ****

    # Check for last update time and display alerts if needed
    now = datetime.datetime.now()

    # show invalid date/time alert
    time_valid = now.year >= 2019
    if time_valid and not time_valid_prev:
      params.delete("Offroad_InvalidTime")
    if not time_valid and time_valid_prev:
      params.put("Offroad_InvalidTime", json.dumps(OFFROAD_ALERTS["Offroad_InvalidTime"]))
    time_valid_prev = time_valid

    # Show update prompt
    try:
      last_update = datetime.datetime.fromisoformat(params.get("LastUpdateTime", encoding='utf8'))
    except (TypeError, ValueError):
      last_update = now
    dt = now - last_update

    if dt.days > DAYS_NO_CONNECTIVITY_MAX:
      if current_connectivity_alert != "expired":
        current_connectivity_alert = "expired"
        params.delete("Offroad_ConnectivityNeededPrompt")
        params.put("Offroad_ConnectivityNeeded", json.dumps(OFFROAD_ALERTS["Offroad_ConnectivityNeeded"]))
    elif dt.days > DAYS_NO_CONNECTIVITY_PROMPT:
      remaining_time = str(DAYS_NO_CONNECTIVITY_MAX - dt.days)
      if current_connectivity_alert != "prompt" + remaining_time:
        current_connectivity_alert = "prompt" + remaining_time
        alert_connectivity_prompt = copy.copy(OFFROAD_ALERTS["Offroad_ConnectivityNeededPrompt"])
        alert_connectivity_prompt["text"] += remaining_time + " days."
        params.delete("Offroad_ConnectivityNeeded")
        params.put("Offroad_ConnectivityNeededPrompt", json.dumps(alert_connectivity_prompt))
    elif current_connectivity_alert is not None:
      current_connectivity_alert = None
      params.delete("Offroad_ConnectivityNeeded")
      params.delete("Offroad_ConnectivityNeededPrompt")

    # start constellation of processes when the car starts
    ignition = health is not None and (health.health.ignitionLine or health.health.ignitionCan)

    do_uninstall = params.get("DoUninstall") == b"1"
    accepted_terms = params.get("HasAcceptedTerms") == terms_version
    completed_training = params.get("CompletedTrainingVersion") == training_version
    fw_version = params.get("PandaFirmware", encoding="utf8")
    fw_version_match = fw_version is None or fw_version.startswith(FW_VERSION)  # don't show alert is no panda is connected (None)

    should_start = ignition

    # with 2% left, we killall, otherwise the phone will take a long time to boot
    should_start = should_start and msg.thermal.freeSpace > 0.02

    # confirm we have completed training and aren't uninstalling
    should_start = should_start and accepted_terms and completed_training and (not do_uninstall)

    # check for firmware mismatch
    #should_start = should_start and fw_version_match

    # check if system time is valid
    should_start = should_start and time_valid

    # don't start while taking snapshot
    if not should_start_prev:
      is_taking_snapshot = params.get("IsTakingSnapshot") == b"1"
      should_start = should_start and (not is_taking_snapshot)

    if fw_version_match and not fw_version_match_prev:
      params.delete("Offroad_PandaFirmwareMismatch")
    if not fw_version_match and fw_version_match_prev:
      params.put("Offroad_PandaFirmwareMismatch", json.dumps(OFFROAD_ALERTS["Offroad_PandaFirmwareMismatch"]))

    # if any CPU gets above 107 or the battery gets above 63, kill all processes
    # controls will warn with CPU above 95 or battery above 60
    if thermal_status >= ThermalStatus.danger:
      should_start = False
      if thermal_status_prev < ThermalStatus.danger:
        params.put("Offroad_TemperatureTooHigh", json.dumps(OFFROAD_ALERTS["Offroad_TemperatureTooHigh"]))
    else:
      if thermal_status_prev >= ThermalStatus.danger:
        params.delete("Offroad_TemperatureTooHigh")

    if should_start:
      off_ts = None
      if started_ts is None:
        started_ts = sec_since_boot()
        started_seen = True
        os.system('echo performance > /sys/class/devfreq/soc:qcom,cpubw/governor')
    else:
      started_ts = None
      if off_ts is None:
        off_ts = sec_since_boot()
        os.system('echo powersave > /sys/class/devfreq/soc:qcom,cpubw/governor')

      # shutdown if the battery gets lower than 3%, it's discharging, we aren't running for
      # more than a minute but we were running
      if msg.thermal.batteryPercent < BATT_PERC_OFF and msg.thermal.batteryStatus == "Discharging" and \
         started_seen and (sec_since_boot() - off_ts) > 60:
        os.system('LD_LIBRARY_PATH="" svc power shutdown')

    charging_disabled = check_car_battery_voltage(should_start, health, charging_disabled, msg)

    if charging_disabled:
      msg.thermal.batteryStatus = "Discharging"
    else:
      msg.thermal.batteryStatus = "Charging"

    
    msg.thermal.chargingDisabled = charging_disabled
    msg.thermal.chargingError = current_filter.x > 0. and msg.thermal.batteryPercent < 90  # if current is positive, then battery is being discharged
    msg.thermal.started = started_ts is not None
    msg.thermal.startedTs = int(1e9*(started_ts or 0))

    msg.thermal.thermalStatus = thermal_status
    thermal_sock.send(msg.to_bytes())

    if usb_power_prev and not usb_power:
      params.put("Offroad_ChargeDisabled", json.dumps(OFFROAD_ALERTS["Offroad_ChargeDisabled"]))
    elif usb_power and not usb_power_prev:
      params.delete("Offroad_ChargeDisabled")

    thermal_status_prev = thermal_status
    usb_power_prev = usb_power
    fw_version_match_prev = fw_version_match
    should_start_prev = should_start

    print(msg)

    # report to server once per minute
    if (count % int(60. / DT_TRML)) == 0:
      cloudlog.event("STATUS_PACKET",
        count=count,
        health=(health.to_dict() if health else None),
        location=(location.to_dict() if location else None),
        thermal=msg.to_dict())

    count += 1


def main(gctx=None):
  thermald_thread()

if __name__ == "__main__":
  main()
