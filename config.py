# Functions and variables for reading INI files.

import json
import os
import sys
from configparser import ConfigParser

from headers import *

SCRIPT_VERSION = "2.0.0"

ini_defaults = {
    "Paths":{
        "MEDIA_PLAYER_PATH":"/usr/local/bin/ffmpeg",
        "RTMP_STREAMER_PATH":"/usr/local/bin/ffmpeg",
        "FFPROBE_PATH":"/usr/local/bin/ffprobe",
        "BASE_PATH":"/media/videos/",
        "MEDIA_PLAYLIST":"playlist.txt",
        "PLAY_INDEX_FILE":"%(BASE_PATH)s/play_index.txt",
        "PLAY_HISTORY_FILE":"%(BASE_PATH)s/play_history.txt",
        "SCHEDULE_PATH":"schedule.json",
        "ALT_NAMES_JSON_PATH":"alt_names.json"
        },
    "VideoOptions":{
        "STREAM_URL":"rtmp://localhost:1935/live/",
        "VIDEO_PADDING":2,
        "MEDIA_PLAYER_ARGUMENTS":"-hide_banner -re -ss {elapsed_time} -i {file} -filter_complex \"[0:v]scale=1280x720,fps=30[scaled];[scaled]tpad=stop_duration=%(VIDEO_PADDING)s;apad=pad_dur=%(VIDEO_PADDING)s\" -c:v h264_omx -b:v 4000k -acodec aac -b:a 192k -ar 48000 -f flv -g 60 rtmp://localhost:1935/live/",
        "RTMP_ARGUMENTS":"-i rtmp://localhost:1935/live -loglevel error -vcodec copy -acodec copy -f flv %(STREAM_URL)s",
        "STREAM_TIME_BEFORE_RESTART":86400,
        "STREAM_RESTART_WAIT":10,
        "STREAM_RESTART_MINIMUM_TIME":1800,
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
    "SFTP":{
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
        "VERBOSE":False
        }
    }

default_ini = ConfigParser(defaults=ini_defaults)
if len(sys.argv) > 1:
    try:
        default_ini.read(sys.argv[1])
        config_file = sys.argv[1]
    except Exception as e:
        print(e)
        print(f"{error} Error reading config file {sys.argv[1]}. Using default values.")
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
                print(f"{error} {config_file} is missing option {option}. Using default configuration.")
                default_ini.read("config.ini")
                config_file = "config.ini"
                break
        else:
            continue
    else:
        print(f"{error} {config_file} is missing section {section}. Using default configuration.")
        default_ini.read("config.ini")
        config_file = "config.ini"
        break

MEDIA_PLAYER_PATH = default_ini.get("Paths","MEDIA_PLAYER_PATH")
RTMP_STREAMER_PATH = default_ini.get("Paths","RTMP_STREAMER_PATH")
FFPROBE_PATH = default_ini.get("Paths","FFPROBE_PATH")
BASE_PATH = os.path.expanduser(default_ini.get("Paths","BASE_PATH"))
PLAY_INDEX_FILE = os.path.expanduser(default_ini.get("Paths","PLAY_INDEX_FILE"))
if default_ini.get("Paths","PLAY_HISTORY_FILE") != "":
    PLAY_HISTORY_FILE = os.path.expanduser(default_ini.get("Paths","PLAY_HISTORY_FILE"))
else:
    PLAY_HISTORY_FILE = None

if default_ini.get("Paths","SCHEDULE_PATH") != "":
    SCHEDULE_PATH = os.path.expanduser(default_ini.get("Paths","SCHEDULE_PATH"))
else:
    SCHEDULE_PATH = None

if default_ini.get("Paths","ALT_NAMES_JSON_PATH") != "":
    ALT_NAMES_JSON_PATH = os.path.expanduser(default_ini.get("Paths","ALT_NAMES_JSON_PATH"))
else:
    ALT_NAMES_JSON_PATH = None

MEDIA_PLAYLIST = os.path.expanduser(default_ini.get("Paths","MEDIA_PLAYLIST"))

MEDIA_PLAYER_ARGUMENTS = default_ini.get("VideoOptions","MEDIA_PLAYER_ARGUMENTS")
RTMP_ARGUMENTS = default_ini.get("VideoOptions","RTMP_ARGUMENTS")
VIDEO_PADDING = default_ini.getint("VideoOptions","VIDEO_PADDING")
STREAM_URL = default_ini.get("VideoOptions","STREAM_URL")
STREAM_TIME_BEFORE_RESTART = default_ini.getint("VideoOptions","STREAM_TIME_BEFORE_RESTART")
STREAM_RESTART_WAIT = default_ini.getint("VideoOptions","STREAM_RESTART_WAIT")
STREAM_RESTART_MINIMUM_TIME = default_ini.getint("VideoOptions","STREAM_RESTART_MINIMUM_TIME")
STREAM_RESTART_BEFORE_VIDEO = default_ini.get("VideoOptions","STREAM_RESTART_BEFORE_VIDEO")
STREAM_RESTART_AFTER_VIDEO = default_ini.get("VideoOptions","STREAM_RESTART_AFTER_VIDEO")

TIME_RECORD_INTERVAL = default_ini.getint("PlayIndex","TIME_RECORD_INTERVAL")
REWIND_LENGTH = default_ini.getint("PlayIndex","REWIND_LENGTH")

SCHEDULE_MAX_VIDEOS = default_ini.getint("Schedule","SCHEDULE_MAX_VIDEOS")
SCHEDULE_UPCOMING_LENGTH = default_ini.getint("Schedule","SCHEDULE_UPCOMING_LENGTH")
SCHEDULE_PREVIOUS_MAX_VIDEOS = default_ini.getint("Schedule","SCHEDULE_PREVIOUS_MAX_VIDEOS")
SCHEDULE_PREVIOUS_LENGTH = default_ini.getint("Schedule","SCHEDULE_PREVIOUS_LENGTH")

if default_ini.get("Schedule","SCHEDULE_EXCLUDE_FILE_PATTERN") != "":
    SCHEDULE_EXCLUDE_FILE_PATTERN = default_ini.get("Schedule","SCHEDULE_EXCLUDE_FILE_PATTERN")
else:
    SCHEDULE_EXCLUDE_FILE_PATTERN = None

RETRY_ATTEMPTS = default_ini.getint("Retry","RETRY_ATTEMPTS")
RETRY_PERIOD = default_ini.getint("Retry","RETRY_PERIOD")
EXIT_ON_FILE_NOT_FOUND = default_ini.getboolean("Retry","EXIT_ON_FILE_NOT_FOUND")

REMOTE_ADDRESS = default_ini.get("SFTP","REMOTE_ADDRESS")
REMOTE_USERNAME = default_ini.get("SFTP","REMOTE_USERNAME")

if default_ini.get("SFTP","REMOTE_PASSWORD") != "":
    REMOTE_PASSWORD = default_ini.get("SFTP","REMOTE_PASSWORD")
else:
    REMOTE_PASSWORD = None

REMOTE_PORT = default_ini.getint("SFTP","REMOTE_PORT")

if default_ini.get("SFTP","REMOTE_KEY_FILE") != "":
    REMOTE_KEY_FILE = default_ini.get("SFTP","REMOTE_KEY_FILE")
else:
    REMOTE_KEY_FILE = None

if default_ini.get("SFTP","REMOTE_KEY_FILE_PASSWORD") != "":
    REMOTE_KEY_FILE_PASSWORD = default_ini.get("SFTP","REMOTE_KEY_FILE_PASSWORD")
else:
    REMOTE_KEY_FILE_PASSWORD = None

REMOTE_DIRECTORY = default_ini.get("SFTP","REMOTE_DIRECTORY")

PLAY_HISTORY_LENGTH = default_ini.getint("Misc","PLAY_HISTORY_LENGTH")
VERBOSE = default_ini.getboolean("Misc","VERBOSE")

# Validate config settings.
if ALT_NAMES_JSON_PATH is not None:
    try:
        with open(ALT_NAMES_JSON_PATH,"r",encoding='utf8') as alt_names_json:
            try:
                ALT_NAMES = json.load(alt_names_json)
            except json.JSONDecodeError as e:
                print(e)
                print(f"{warn} Error loading {ALT_NAMES_JSON_PATH} in ALT_NAMES_JSON_PATH.")
                ALT_NAMES = {}

    except FileNotFoundError:
        print(f"{warn} {ALT_NAMES_JSON_PATH} in ALT_NAMES_JSON_PATH not found.")
        ALT_NAMES_JSON_PATH = None
        ALT_NAMES = {}
else:
    ALT_NAMES = {}

if SCHEDULE_EXCLUDE_FILE_PATTERN is not None:
    SCHEDULE_EXCLUDE_FILE_PATTERN = tuple([i.strip().casefold().replace("\\","/") for i in SCHEDULE_EXCLUDE_FILE_PATTERN.split(",")])

# STREAM_RESTART_BEFORE_VIDEO and STREAM_RESTART_AFTER_VIDEO are only checked
# as existing once at startup.
if STREAM_RESTART_BEFORE_VIDEO != "":
    if not os.path.isfile(STREAM_RESTART_BEFORE_VIDEO):
        if not EXIT_ON_FILE_NOT_FOUND:
            print(f"{warn} STREAM_RESTART_BEFORE_VIDEO not found.")
            STREAM_RESTART_BEFORE_VIDEO = None
else:
    STREAM_RESTART_BEFORE_VIDEO = None

if STREAM_RESTART_AFTER_VIDEO != "":
    if not os.path.isfile(STREAM_RESTART_AFTER_VIDEO):
        if not EXIT_ON_FILE_NOT_FOUND:
            print(f"{warn} STREAM_RESTART_AFTER_VIDEO not found.")
            STREAM_RESTART_AFTER_VIDEO = None
else:
    STREAM_RESTART_AFTER_VIDEO = None


if __name__ == "__main__":
    print("Run python3 main.py to start this program.")