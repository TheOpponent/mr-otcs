# Functions and variables for reading INI files.

import json
import os
import sys
from configparser import ConfigParser

SCRIPT_VERSION = "2.0.0"

ini_defaults = {
    "Paths":{
        "MEDIA_PLAYER_PATH":"/usr/bin/ffmpeg",
        "RTMP_STREAMER_PATH":"/usr/local/bin/ffmpeg",
        "BASE_PATH":"/media/videos/",
        "MEDIA_PLAYLIST":"playlist.txt",
        "PLAY_INDEX_FILE":"%(BASE_PATH)s/play_index.txt",
        "PLAY_HISTORY_FILE":"%(BASE_PATH)s/play_history.txt",
        "SCHEDULE_PATH":"schedule.json",
        "ALT_NAMES_JSON_PATH":"alt_names.json"
        },
    "VideoOptions":{
        "STREAM_URL":"rtmp://localhost:1935/live/",
        "CHECK_URL":"https://google.com",
        "CHECK_INTERVAL":60,
        "VIDEO_PADDING":2,
        "MEDIA_PLAYER_ARGUMENTS":"-hide_banner -re -ss {elapsed_time} -i \"{file}\" -filter_complex \"[0:v]scale=1280x720,fps=30[scaled];[scaled]tpad=stop_duration=%(VIDEO_PADDING)s;apad=pad_dur=%(VIDEO_PADDING)s\" -c:v h264_omx -b:v 4000k -acodec aac -b:a 192k -ar 48000 -f flv -g 60 rtmp://localhost:1935/live/",
        "RTMP_ARGUMENTS":"-i rtmp://localhost:1935/live -loglevel error -vcodec copy -acodec copy -f flv %(STREAM_URL)s",
        "STREAM_TIME_BEFORE_RESTART":1440,
        "STREAM_RESTART_WAIT":10,
        "STREAM_RESTART_MINIMUM_TIME":30,
        "STREAM_RESTART_BEFORE_VIDEO":"",
        "STREAM_RESTART_AFTER_VIDEO":""
        },
    "PlayIndex":{
        "TIME_RECORD_INTERVAL":30,
        "REWIND_LENGTH":30
        },
    "Schedule":{
        "SCHEDULE_MAX_VIDEOS":15,
        "SCHEDULE_UPCOMING_LENGTH":240,
        "SCHEDULE_PREVIOUS_MAX_VIDEOS":3,
        "SCHEDULE_UPCOMING_LENGTH":30,
        "SCHEDULE_EXCLUDE_FILE_PATTERN":""
        },
    "Retry":{
        "RETRY_ATTEMPTS":0,
        "RETRY_PERIOD":5,
        "EXIT_ON_FILE_NOT_FOUND":False
        },
    "SSH":{
        "REMOTE_ADDRESS":"",
        "REMOTE_USERNAME":"",
        "REMOTE_PASSWORD":"",
        "REMOTE_PORT":22,
        "REMOTE_KEY_FILE":"",
        "REMOTE_KEY_FILE_PASSWORD":"",
        "REMOTE_DIRECTORY":""
        },
    "Misc":{
        "PLAY_HISTORY_LENGTH":10,
        "VERBOSE":"info"
        }
    }

default_ini = ConfigParser(defaults=ini_defaults)
if len(sys.argv) > 1:
    try:
        default_ini.read(sys.argv[1])
        config_file = sys.argv[1]
    except Exception as e:
        print(e)
        print(f"Error reading config file {sys.argv[1]}. Using default values.")
        default_ini.read("config.ini")
        config_file = "config.ini"
else:
    default_ini.read("config.ini")
    config_file = "config.ini"

# Basic validation of config file structure.
for section in ini_defaults:
    if default_ini.has_section(section):
        for option in ini_defaults[section]:
            if default_ini.has_option(section,option):
                continue
            else:
                print(f"{config_file} is missing option {option}. Using default configuration.")
                default_ini.read("config.ini")
                config_file = "config.ini"
                break
        else:
            continue
    else:
        print(f"{config_file} is missing section {section}. Using default configuration.")
        default_ini.read("config.ini")
        config_file = "config.ini"
        break

MEDIA_PLAYER_PATH = default_ini.get("Paths","MEDIA_PLAYER_PATH")
RTMP_STREAMER_PATH = default_ini.get("Paths","RTMP_STREAMER_PATH")
BASE_PATH = os.path.expanduser(default_ini.get("Paths","BASE_PATH"))
PLAY_INDEX_FILE = os.path.expanduser(default_ini.get("Paths","PLAY_INDEX_FILE"))
PLAY_HISTORY_FILE = os.path.expanduser(default_ini.get("Paths","PLAY_HISTORY_FILE")) if default_ini.get("Paths","PLAY_HISTORY_FILE") != "" else None
SCHEDULE_PATH = os.path.expanduser(default_ini.get("Paths","SCHEDULE_PATH")) if default_ini.get("Paths","SCHEDULE_PATH") != "" else None
ALT_NAMES_JSON_PATH = os.path.expanduser(default_ini.get("Paths","ALT_NAMES_JSON_PATH")) if default_ini.get("Paths","ALT_NAMES_JSON_PATH") != "" else None

MEDIA_PLAYLIST = os.path.expanduser(default_ini.get("Paths","MEDIA_PLAYLIST"))

MEDIA_PLAYER_ARGUMENTS = default_ini.get("VideoOptions","MEDIA_PLAYER_ARGUMENTS")
RTMP_ARGUMENTS = default_ini.get("VideoOptions","RTMP_ARGUMENTS")
VIDEO_PADDING = default_ini.getint("VideoOptions","VIDEO_PADDING")
STREAM_URL = default_ini.get("VideoOptions","STREAM_URL")
CHECK_URL = default_ini.get("VideoOptions","CHECK_URL")
CHECK_INTERVAL = default_ini.getint("VideoOptions","CHECK_INTERVAL")
STREAM_TIME_BEFORE_RESTART = default_ini.getint("VideoOptions","STREAM_TIME_BEFORE_RESTART") * 60
STREAM_RESTART_WAIT = default_ini.getint("VideoOptions","STREAM_RESTART_WAIT")
STREAM_RESTART_MINIMUM_TIME = default_ini.getint("VideoOptions","STREAM_RESTART_MINIMUM_TIME") * 60
if default_ini.get("VideoOptions","STREAM_RESTART_BEFORE_VIDEO") != "":
    STREAM_RESTART_BEFORE_VIDEO = os.path.join(BASE_PATH,default_ini.get("VideoOptions","STREAM_RESTART_BEFORE_VIDEO"))
else:
    STREAM_RESTART_BEFORE_VIDEO = None
if default_ini.get("VideoOptions","STREAM_RESTART_AFTER_VIDEO") != "":
    STREAM_RESTART_AFTER_VIDEO = os.path.join(BASE_PATH,default_ini.get("VideoOptions","STREAM_RESTART_AFTER_VIDEO"))
else:
    STREAM_RESTART_AFTER_VIDEO = None

TIME_RECORD_INTERVAL = default_ini.getint("PlayIndex","TIME_RECORD_INTERVAL")
REWIND_LENGTH = default_ini.getint("PlayIndex","REWIND_LENGTH")

SCHEDULE_MAX_VIDEOS = default_ini.getint("Schedule","SCHEDULE_MAX_VIDEOS")
SCHEDULE_UPCOMING_LENGTH = default_ini.getint("Schedule","SCHEDULE_UPCOMING_LENGTH") * 60
SCHEDULE_PREVIOUS_MAX_VIDEOS = default_ini.getint("Schedule","SCHEDULE_PREVIOUS_MAX_VIDEOS")
SCHEDULE_PREVIOUS_LENGTH = default_ini.getint("Schedule","SCHEDULE_PREVIOUS_LENGTH") * 60

if default_ini.get("Schedule","SCHEDULE_EXCLUDE_FILE_PATTERN") != "":
    SCHEDULE_EXCLUDE_FILE_PATTERN = tuple([i.strip().casefold().replace("\\","/") for i in default_ini.get("Schedule","SCHEDULE_EXCLUDE_FILE_PATTERN").split(",")])
else:
    SCHEDULE_EXCLUDE_FILE_PATTERN = None

RETRY_ATTEMPTS = default_ini.getint("Retry","RETRY_ATTEMPTS")
RETRY_PERIOD = default_ini.getint("Retry","RETRY_PERIOD")
EXIT_ON_FILE_NOT_FOUND = default_ini.getboolean("Retry","EXIT_ON_FILE_NOT_FOUND")

REMOTE_ADDRESS = default_ini.get("SSH","REMOTE_ADDRESS") if default_ini.get("SSH","REMOTE_ADDRESS") != "" else None
REMOTE_USERNAME = default_ini.get("SSH","REMOTE_USERNAME") if default_ini.get("SSH","REMOTE_USERNAME") != "" else None
REMOTE_PASSWORD = default_ini.get("SSH","REMOTE_PASSWORD") if default_ini.get("SSH","REMOTE_PASSWORD") != "" else None
REMOTE_PORT = default_ini.getint("SSH","REMOTE_PORT") if default_ini.getint("SSH","REMOTE_PORT") != "" else 22
REMOTE_KEY_FILE = default_ini.get("SSH","REMOTE_KEY_FILE") if default_ini.get("SSH","REMOTE_KEY_FILE") != "" else None
REMOTE_KEY_FILE_PASSWORD = default_ini.get("SSH","REMOTE_KEY_FILE_PASSWORD") if default_ini.get("SSH","REMOTE_KEY_FILE_PASSWORD") != "" else None
REMOTE_DIRECTORY = default_ini.get("SSH","REMOTE_DIRECTORY") if default_ini.get("SSH","REMOTE_DIRECTORY") != "" else None

PLAY_HISTORY_LENGTH = default_ini.getint("Misc","PLAY_HISTORY_LENGTH")
VERBOSE = default_ini.get("Misc","VERBOSE").lower()

if VERBOSE == "fatal":
    VERBOSE = 0b10000000
elif VERBOSE == "error":
    VERBOSE = 0b11000000
elif VERBOSE == "warn":
    VERBOSE = 0b11100000
elif VERBOSE == "notice":
    VERBOSE = 0b11110000
elif VERBOSE == "play":
    VERBOSE = 0b11111000
elif VERBOSE == "info":
    VERBOSE = 0b11111100
elif VERBOSE == "verbose":
    VERBOSE = 0b11111110
elif VERBOSE == "verbose2":
    VERBOSE = 0b11111111
else:
    print("VERBOSE setting not recognized. Using default setting \"info\".")
    VERBOSE = 0b11111100

reset = '\033[0m'
notice = '\033[96m' + "[Notice]" + reset
warn = '\033[93m' + "[Warn]" + reset
error = '\033[31m' + "[Error]" + reset
play = '\033[92m' + "[Play]" + reset

def print2(level: str,message: str):
    """Prepend a colored label with a standard print message."""

    if level == "fatal" and VERBOSE & 0b10000000:
        print(f"{error} {message}")
    elif level == "error" and VERBOSE & 0b1000000:
        print(f"{error} {message}")
    elif level == "warn" and VERBOSE & 0b100000:
        print(f"{warn} {message}")
    elif level == "notice" and VERBOSE & 0b10000:
        print(f"{notice} {message}")
    elif level == "play" and VERBOSE & 0b1000:
        print(f"{play} {message}")
    elif level == "info" and VERBOSE & 0b100:
        print(f"[Info] {message}")
    elif level == "verbose" and VERBOSE & 0b10:
        print(f"[Info] {message}")
    elif level == "verbose2" and VERBOSE & 0b1:
        print(f"[Info] {message}")


# Validate config settings.
if ALT_NAMES_JSON_PATH is not None:
    try:
        with open(ALT_NAMES_JSON_PATH,"r",encoding='utf8') as alt_names_json:
            try:
                ALT_NAMES = json.load(alt_names_json)
                print2("verbose",f"{len(ALT_NAMES)} keys loaded from {ALT_NAMES_JSON_PATH}.")
            except json.JSONDecodeError as e:
                print(e)
                print2("error",f"Error loading {ALT_NAMES_JSON_PATH} in ALT_NAMES_JSON_PATH.")
                ALT_NAMES = {}

    except FileNotFoundError:
        print2("error",f"{ALT_NAMES_JSON_PATH} in ALT_NAMES_JSON_PATH not found.")
        ALT_NAMES_JSON_PATH = None
        ALT_NAMES = {}
else:
    ALT_NAMES = {}

# STREAM_RESTART_BEFORE_VIDEO and STREAM_RESTART_AFTER_VIDEO are only checked
# as existing once at startup.
if STREAM_RESTART_BEFORE_VIDEO is not None:
    if not os.path.isfile(STREAM_RESTART_BEFORE_VIDEO):
        print2("error",f"STREAM_RESTART_BEFORE_VIDEO not found.")
        if not EXIT_ON_FILE_NOT_FOUND:
            STREAM_RESTART_BEFORE_VIDEO = None
        else:
            exit(1)
else:
    STREAM_RESTART_BEFORE_VIDEO = None

if STREAM_RESTART_AFTER_VIDEO is not None:
    if not os.path.isfile(STREAM_RESTART_AFTER_VIDEO):
        print2("error",f"STREAM_RESTART_AFTER_VIDEO not found.")
        if not EXIT_ON_FILE_NOT_FOUND:
            STREAM_RESTART_AFTER_VIDEO = None
        else:
            exit(1)
else:
    STREAM_RESTART_AFTER_VIDEO = None

# Enforce a minimum of 10 seconds for safety.
if CHECK_INTERVAL < 10:
    CHECK_INTERVAL = 10


if __name__ == "__main__":
    print("Run python3 main.py to start this program.")