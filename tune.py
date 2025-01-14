import sys
import termios
import tty
import os
import time
from selfdrive.kegman_conf import KegmanConf

BASEDIR = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "../"))
button_delay = 0.2

# letters stolen from here: http://www.stuffaboutcode.com/2013/08/raspberry-pi-minecraft-twitter.html
letters = {"a": ["###", "# #", "###", "# #", "# #"], "b": ["###", "# #", "###", "# #", "###"],
           "c": ["###", "#", "#", "#", "###"], "d": ["##", "# #", "# #", "# #", "##"],
           "e": ["###", "#", "###", "#", "###"], "f": ["###", "#", "###", "#", "#"],
           "g": ["###", "# #", "###", "  #", "###"], "h": ["# #", "# #", "###", "# #", "# #"],
           "i": ["###", " #", " #", " #", "###"], "j": ["###", " #", " #", " #", "##"],
           "k": ["# #", "##", "#", "##", "# #"], "l": ["#", "#", "#", "#", "###"],
           "m": ["# #", "###", "###", "# #", "# #"], "n": ["###", "# #", "# #", "# #", "# #"],
           "o": ["###", "# #", "# #", "# #", "###"], "p": ["###", "# #", "###", "#", "#"],
           "q": ["###", "# #", "###", "  #", "  #"], "r": ["###", "# #", "##", "# #", "# #"],
           "s": ["###", "#", "###", "  #", "###"], "t": ["###", " #", " #", " #", " #"],
           "u": ["# #", "# #", "# #", "# #", "###"], "v": ["# #", "# #", "# #", "# #", " #"],
           "w": ["# #", "# #", "# #", "###", "###"], "x": ["# #", " #", " #", " #", "# #"],
           "y": ["# #", "# #", "###", "  #", "###"], "z": ["###", "  #", " #", "#", "###"], " ": [" "],
           "1": [" #", "##", " #", " #", "###"], "2": ["###", "  #", "###", "#", "###"],
           "3": ["###", "  #", "###", "  #", "###"], "4": ["#", "#", "# #", "###", "  #"],
           "5": ["###", "#", "###", "  #", "###"], "6": ["###", "#", "###", "# #", "###"],
           "7": ["###", "  # ", " #", " #", "#"], "8": ["###", "# #", "###", "# #", "###"],
           "9": ["###", "# #", "###", "  #", "###"], "0": ["###", "# #", "# #", "# #", "###"],
           "!": [" # ", " # ", " # ", "   ", " # "], "?": ["###", "  #", " ##", "   ", " # "],
           ".": ["   ", "   ", "   ", "   ", " # "], "]": ["   ", "   ", "   ", "  #", " # "],
           "/": ["  #", "  #", " # ", "# ", "# "], ":": ["   ", " # ", "   ", " # ", "   "],
           "@": ["###", "# #", "## ", "#  ", "###"], "'": [" # ", " # ", "   ", "   ", "   "],
           "#": [" # ", "###", " # ", "###", " # "], "-": ["  ", "  ", "###", "   ", "   "]}


def print_letters(text):
  bigletters = []
  for i in text:
    bigletters.append(letters.get(i.lower(), letters[' ']))
  output = [''] * 5
  for i in range(5):
    for j in bigletters:
      temp = ' '
      try:
        temp = j[i]
      except:
        pass
      temp += ' ' * (5 - len(temp))
      temp = temp.replace(' ', ' ')
      temp = temp.replace('#', '@')
      output[i] += temp
  return '\n'.join(output)


def getch():
  fd = sys.stdin.fileno()
  old_settings = termios.tcgetattr(fd)
  try:
    tty.setraw(sys.stdin.fileno())
    ch = sys.stdin.read(1)

  finally:
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
  return ch

params = ["Kp", "Ki", "Kf", "steerRatio", "steerRateCost", "steerActuatorDelay",
         "deadzone", "sR_boost", "sR_BP0", "sR_BP1", "sR_time", "slowOnCurves",
         "1barBP0", "1barBP1", "1barMax", "2barBP0", "2barBP1",
         "2barMax", "3barBP0", "3barBP1", "3barMax",
         "1barHwy", "2barHwy", "3barHwy"]

kegman = KegmanConf()
kegman.conf['tuneGernby'] = "1"
# kegman.write_config(kegman.conf)

j = 0
while True:
  print("")
  print(print_letters(params[j][0:9]))
  print("")
  print(print_letters(kegman.conf[params[j]]))
  print("")
  print("1,3,5,7,r to incr 0.1,0.05,0.01,0.001,0.00001")
  print("a,d,g,j,v to decr 0.1,0.05,0.01,0.001,0.00001")
  print("0 / L to make the value 0 / 1")
  print("press SPACE / m for next /prev parameter")
  print("press z to quit")

  char = getch()
  write_json = False

  if (char == "z"):
    sys.exit(0)

  elif (char == " "):
    j += 1
    if j == len(params):
      j = 0

  elif (char == "m"):
    j -= 1
    if j < 0:
      j = len(params) - 1

  elif (char == "v"):
    kegman.conf[params[j]] = str(round((float(kegman.conf[params[j]]) - 0.00001), 5))
    write_json = True

  elif (char == "r"):
    kegman.conf[params[j]] = str(round((float(kegman.conf[params[j]]) + 0.00001), 5))
    write_json = True

  elif (char == "7"):
    kegman.conf[params[j]] = str(round((float(kegman.conf[params[j]]) + 0.001), 5))
    write_json = True

  elif (char == "5"):
    kegman.conf[params[j]] = str(round((float(kegman.conf[params[j]]) + 0.01), 5))
    write_json = True

  elif (char == "3"):
    kegman.conf[params[j]] = str(round((float(kegman.conf[params[j]]) + 0.05), 5))
    write_json = True

  elif (char == "1"):
    kegman.conf[params[j]] = str(round((float(kegman.conf[params[j]]) + 0.1), 5))
    write_json = True

  elif (char == "j"):
    kegman.conf[params[j]] = str(round((float(kegman.conf[params[j]]) - 0.001), 5))
    write_json = True

  elif (char == "g"):
    kegman.conf[params[j]] = str(round((float(kegman.conf[params[j]]) - 0.01), 5))
    write_json = True

  elif (char == "d"):
    kegman.conf[params[j]] = str(round((float(kegman.conf[params[j]]) - 0.05), 5))
    write_json = True

  elif (char == "a"):
    kegman.conf[params[j]] = str(round((float(kegman.conf[params[j]]) - 0.1), 5))
    write_json = True

  elif (char == "0"):
    kegman.conf[params[j]] = "0"
    write_json = True

  elif (char == "l"):
    kegman.conf[params[j]] = "1"
    write_json = True

  if float(kegman.conf['Kp']) < 0 and float(kegman.conf['Kp']) != -1:
    kegman.conf['Kp'] = "0"

  if float(kegman.conf['Kp']) > 3:
    kegman.conf['Kp'] = "3"

  if float(kegman.conf['Ki']) < 0 and float(kegman.conf['Ki']) != -1:
    kegman.conf['Ki'] = "0"

  if float(kegman.conf['Ki']) > 2:
    kegman.conf['Ki'] = "2"

  if float(kegman.conf['Kf']) < 0 and float(kegman.conf['Kp']) != -1:
    kegman.conf['Kf'] = "0"

  if float(kegman.conf['Kf']) > 0.01:
    kegman.conf['Kf'] = "0.01"

  # if float(kegman.conf['Kf']) < 0.00001:
  kegman.conf['Kf'] = str("{:.5f}".format(float(kegman.conf['Kf'])))

  if float(kegman.conf['steerRatio']) < 1 and float(kegman.conf['steerRatio']) != -1:
    kegman.conf['steerRatio'] = "1"

  if float(kegman.conf['steerRateCost']) < 0.01 and float(kegman.conf['steerRateCost']) != -1:
    kegman.conf['steerRateCost'] = "0.01"

  if float(kegman.conf['steerActuatorDelay']) < 0.1 and float(kegman.conf['steerActuatorDelay']) != -1:
    kegman.conf['steerRateCost'] = "0.1"

  if float(kegman.conf['deadzone']) < 0:
    kegman.conf['deadzone'] = "0"

  if float(kegman.conf['tuneGernby']) != 1 and float(kegman.conf['tuneGernby']) != 0:
    kegman.conf['tuneGernby'] = "1"

  if kegman.conf['liveParams'] != "1" and kegman.conf['liveParams'] != "0":
    kegman.conf['liveParams'] = "1"

  if float(kegman.conf['1barBP0']) < -0.5:
    kegman.conf['1barBP0'] = "-0.5"

  if float(kegman.conf['1barBP0']) > 0.5:
    kegman.conf['1barBP0'] = "0.5"

  if float(kegman.conf['1barBP1']) < 0.5:
    kegman.conf['1barBP1'] = "0.5"

  if float(kegman.conf['1barBP1']) > 8:
    kegman.conf['1barBP1'] = "8"

  if float(kegman.conf['1barMax']) < 0.9:
    kegman.conf['1barMax'] = "0.9"

  if float(kegman.conf['1barMax']) > 2.5:
    kegman.conf['1barMax'] = "2.5"

  if float(kegman.conf['2barBP0']) < -0.5:
    kegman.conf['2barBP0'] = "-0.5"

  if float(kegman.conf['2barBP0']) > 0.5:
    kegman.conf['2barBP0'] = "0.5"

  if float(kegman.conf['2barBP1']) < 0.5:
    kegman.conf['2barBP1'] = "0.5"

  if float(kegman.conf['2barBP1']) > 8:
    kegman.conf['2barBP1'] = "8"

  if float(kegman.conf['2barMax']) < 1.3:
    kegman.conf['2barMax'] = "1.3"

  if float(kegman.conf['2barMax']) > 2.5:
    kegman.conf['2barMax'] = "2.5"

  if float(kegman.conf['3barBP0']) < -0.5:
    kegman.conf['3barBP0'] = "-0.5"

  if float(kegman.conf['3barBP0']) > 0.5:
    kegman.conf['3barBP0'] = "0.5"

  if float(kegman.conf['3barBP1']) < 0.5:
    kegman.conf['3barBP1'] = "0.5"

  if float(kegman.conf['3barBP1']) > 8:
    kegman.conf['3barBP1'] = "8"

  if float(kegman.conf['3barMax']) < 1.8:
    kegman.conf['3barMax'] = "1.8"

  if float(kegman.conf['3barMax']) > 2.5:
    kegman.conf['3barMax'] = "2.5"

  if float(kegman.conf['1barHwy']) < 0:
    kegman.conf['1barHwy'] = "0"

  if float(kegman.conf['2barHwy']) < 0:
    kegman.conf['2barHwy'] = "0"

  if float(kegman.conf['3barHwy']) < 0:
    kegman.conf['3barHwy'] = "0"

  if float(kegman.conf['1barHwy']) > 2:
    kegman.conf['1barHwy'] = "2"

  if float(kegman.conf['2barHwy']) > 2:
    kegman.conf['2barHwy'] = "2"

  if float(kegman.conf['3barHwy']) > 2:
    kegman.conf['3barHwy'] = "2"

  if float(kegman.conf['sR_boost']) < 0:
    kegman.conf['sR_boost'] = "0"

  if float(kegman.conf['sR_BP0']) < 0:
    kegman.conf['sR_BP0'] = "0"

  if float(kegman.conf['sR_BP1']) < 0:
    kegman.conf['sR_BP1'] = "0"

  if float(kegman.conf['sR_time']) < 1:
    kegman.conf['sR_time'] = "1"

  if float(kegman.conf['slowOnCurves']) > 0.00001:
    kegman.conf['slowOnCurves'] = "1"

  if float(kegman.conf['slowOnCurves']) <= 0.99999:
    kegman.conf['slowOnCurves'] = "0"

  if write_json:
    kegman.write_config(kegman.conf)

  time.sleep(button_delay)
