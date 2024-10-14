"""Functions and variables for reading INI files."""

import datetime
import json
import os
import sys
import configparser

SCRIPT_VERSION = "2.2.0-beta3"

ini_defaults = {
    "Paths": {
        "MEDIA_PLAYER_PATH": "/usr/bin/ffmpeg",
        "RTMP_STREAMER_PATH": "/usr/local/bin/ffmpeg",
        "BASE_PATH": "/media/videos/",
        "MEDIA_PLAYLIST": "playlist.txt",
        "PLAY_INDEX_FILE": "%(BASE_PATH)s/play_index.txt",
        "PLAY_HISTORY_FILE": "%(BASE_PATH)s/play_history.txt",
        "SCHEDULE_PATH": "schedule.json",
        "ALT_NAMES_JSON_PATH": "alt_names.json",
        "MEDIA_PLAYER_LOG": "ffmpeg_media.log",
        "RTMP_STREAMER_LOG": "ffmpeg_rtmp.log",
        "ERROR_LOG": "error.log",
    },
    "VideoOptions": {
        "STREAM_URL": "rtmp://localhost:1935/live/",
        "CHECK_URL": "https://google.com, https://twitch.tv, https://github.com, https://amazon.com, https://canhazip.com, https://one.one.one.one, https://8.8.8.8",
        "CHECK_INTERVAL": 60,
        "CHECK_STRICT": True,
        "VIDEO_PADDING": 2,
        "MEDIA_PLAYER_ARGUMENTS": '-hide_banner -loglevel fatal -re -ss {skip_time} -i {file} -filter_complex "[0:v]scale=1280x720,fps=30[scaled];[scaled]tpad=stop_duration={video_padding};apad=pad_dur={video_padding}" -c:v h264_v4l2m2m -b:v 4000k -acodec aac -b:a 192k -ar 48000 -f flv -g 60 rtmp://localhost:1935/live/',
        "RTMP_ARGUMENTS": "-hide_banner -loglevel fatal -i rtmp://localhost:1935/live -vcodec copy -acodec copy -f flv %(STREAM_URL)s",
        "STREAM_TIME_BEFORE_RESTART": 1440,
        "STREAM_RESTART_WAIT": 10,
        "STREAM_RESTART_MINIMUM_TIME": 30,
        "STREAM_RESTART_BEFORE_VIDEO": "",
        "STREAM_RESTART_AFTER_VIDEO": "",
        "STREAM_WAIT_AFTER_RETRY": 15,
        "STOP_AFTER_LAST_VIDEO": False,
    },
    "PlayIndex": {
        "TIME_RECORD_INTERVAL": 30,
        "REWIND_LENGTH": 30,
    },
    "Schedule": {
        "SCHEDULE_MIN_VIDEOS": 1,
        "SCHEDULE_MAX_VIDEOS": 15,
        "SCHEDULE_UPCOMING_LENGTH": 240,
        "SCHEDULE_PREVIOUS_MAX_VIDEOS": 3,
        "SCHEDULE_PREVIOUS_LENGTH": 30,
        "SCHEDULE_PREVIOUS_PRUNE_TIGHT": False,
        "SCHEDULE_EXCLUDE_FILE_PATTERN": "",
        "SCHEDULE_OFFSET": 0,
    },
    "Retry": {
        "RETRY_ATTEMPTS": 0,
        "RETRY_PERIOD": 5,
        "EXIT_ON_FILE_NOT_FOUND": False,
    },
    "SSH": {
        "REMOTE_ADDRESS": "",
        "REMOTE_USERNAME": "",
        "REMOTE_PASSWORD": "",
        "REMOTE_PORT": 22,
        "REMOTE_KEY_FILE": "",
        "REMOTE_KEY_FILE_PASSWORD": "",
        "REMOTE_DIRECTORY": "",
        "REMOTE_UPLOAD_ATTEMPTS": 5,
        "REMOTE_RETRY_PERIOD": 5,
    },
    "Mail": {
        "MAIL_ENABLE": False,
        "MAIL_ENV_CONFIG": False,
        "MAIL_ENV_PREFIX": "MR_OTCS_",
        "MAIL_USE_SSL": False,
        "MAIL_USE_STARTTLS": False,
        "MAIL_SERVER": "",
        "MAIL_PORT": 0,
        "MAIL_LOGIN": "",
        "MAIL_PASSWORD": "",
        "MAIL_FROM_ADDRESS": "",
        "MAIL_TO_ADDRESS": "",
        "MAIL_PROGRAM_NAME": "Mr. OTCS",
        "MAIL_ALERT_ON_STREAM_DOWN": True,
        "MAIL_ALERT_ON_STREAM_RESUME": True,
        "MAIL_ALERT_ON_STREAM_COMMAND": True,
        "MAIL_ALERT_ON_PROGRAM_ERROR": True,
        "MAIL_ALERT_ON_REMOTE_ERROR": True,
        "MAIL_ALERT_MAX_ERRORS_REPORTED": 50,
        "MAIL_ALERT_ON_PLAYLIST_LOOP": False,
        "MAIL_ALERT_ON_PLAYLIST_STOP": True,
        "MAIL_ALERT_ON_PLAYLIST_END": True,
        "MAIL_ALERT_ON_NEW_VERSION": True,
        "MAIL_ALERT_ON_NEW_PRERELEASE_VERSION": False,
        "MAIL_ALERT_STATUS_REPORT": 7,
    },
    "Misc": {
        "PLAY_HISTORY_LENGTH": 10,
        "VERBOSE": "info",
        "STREAM_MANUAL_RESTART_DELAY": 5,
        "VERSION_CHECK_INTERVAL": "monthly",
    },
}

default_ini = configparser.ConfigParser(defaults=ini_defaults)

if len(sys.argv) > 1:
    try:
        config_file = sys.argv[1]
        default_ini.read_dict(ini_defaults)
        default_ini.read(sys.argv[1])
    except configparser.Error as e:
        print(f"Error reading config file {sys.argv[1]}: {e}")
        sys.exit(1)
else:
    config_file = os.getenv("MR_OTCS_CONFIG_INI", "config.ini")
    default_ini.read_dict(ini_defaults)
    default_ini.read(config_file)


MEDIA_PLAYER_PATH = default_ini.get("Paths", "MEDIA_PLAYER_PATH")
RTMP_STREAMER_PATH = default_ini.get("Paths", "RTMP_STREAMER_PATH")
BASE_PATH = os.path.expanduser(default_ini.get("Paths", "BASE_PATH"))
PLAY_INDEX_FILE = os.path.expanduser(default_ini.get("Paths", "PLAY_INDEX_FILE"))
PLAY_HISTORY_FILE = (
    os.path.expanduser(default_ini.get("Paths", "PLAY_HISTORY_FILE"))
    if default_ini.get("Paths", "PLAY_HISTORY_FILE") != ""
    else None
)
SCHEDULE_PATH = (
    os.path.expanduser(default_ini.get("Paths", "SCHEDULE_PATH"))
    if default_ini.get("Paths", "SCHEDULE_PATH") != ""
    else None
)
ALT_NAMES_JSON_PATH = (
    os.path.expanduser(default_ini.get("Paths", "ALT_NAMES_JSON_PATH"))
    if default_ini.get("Paths", "ALT_NAMES_JSON_PATH") != ""
    else None
)
if default_ini.has_option("Paths", "MEDIA_PLAYER_LOG"):  # Added in 2.2.0.
    MEDIA_PLAYER_LOG = (
        os.path.expanduser(default_ini.get("Paths", "MEDIA_PLAYER_LOG"))
        if default_ini.get("Paths", "MEDIA_PLAYER_LOG") != ""
        else None
    )
else:
    MEDIA_PLAYER_LOG = "ffmpeg_media.log"
if default_ini.has_option("Paths", "RTMP_STREAMER_LOG"):  # Added in 2.2.0.
    RTMP_STREAMER_LOG = (
        os.path.expanduser(default_ini.get("Paths", "RTMP_STREAMER_LOG"))
        if default_ini.get("Paths", "RTMP_STREAMER_LOG") != ""
        else None
    )
else:
    RTMP_STREAMER_LOG = "ffmpeg_rtmp.log"
if default_ini.has_option("Paths", "ERROR_LOG"):  # Added in 2.2.0.
    ERROR_LOG = (
        os.path.expanduser(default_ini.get("Paths", "ERROR_LOG"))
        if default_ini.get("Paths", "ERROR_LOG") != ""
        else None
    )
else:
    ERROR_LOG = "error.log"

MEDIA_PLAYLIST = os.path.expanduser(default_ini.get("Paths", "MEDIA_PLAYLIST"))

MEDIA_PLAYER_ARGUMENTS = default_ini.get("VideoOptions", "MEDIA_PLAYER_ARGUMENTS")
RTMP_ARGUMENTS = default_ini.get("VideoOptions", "RTMP_ARGUMENTS")
VIDEO_PADDING = default_ini.getint("VideoOptions", "VIDEO_PADDING")
STREAM_URL = default_ini.get("VideoOptions", "STREAM_URL")
if default_ini.get("VideoOptions", "CHECK_URL") != "":
    CHECK_URL = [
        i.strip() for i in default_ini.get("VideoOptions", "CHECK_URL").split(",")
    ]
else:
    CHECK_URL = None
if default_ini.has_option("VideoOptions", "CHECK_INTERVAL"):
    CHECK_INTERVAL = default_ini.getint("VideoOptions", "CHECK_INTERVAL")
else:
    CHECK_INTERVAL = 60
CHECK_STRICT = default_ini.getboolean("VideoOptions", "CHECK_STRICT")  # Added in 2.2.0.
STREAM_TIME_BEFORE_RESTART = (
    default_ini.getint("VideoOptions", "STREAM_TIME_BEFORE_RESTART") * 60
)
STREAM_RESTART_WAIT = default_ini.getint("VideoOptions", "STREAM_RESTART_WAIT")
STREAM_RESTART_MINIMUM_TIME = (
    default_ini.getint("VideoOptions", "STREAM_RESTART_MINIMUM_TIME") * 60
)
if default_ini.get("VideoOptions", "STREAM_RESTART_BEFORE_VIDEO") != "":
    STREAM_RESTART_BEFORE_VIDEO = default_ini.get(
        "VideoOptions", "STREAM_RESTART_BEFORE_VIDEO"
    )
    if not os.path.isabs(STREAM_RESTART_BEFORE_VIDEO):
        STREAM_RESTART_BEFORE_VIDEO = os.path.join(
            BASE_PATH, STREAM_RESTART_BEFORE_VIDEO
        )
else:
    STREAM_RESTART_BEFORE_VIDEO = None
if default_ini.get("VideoOptions", "STREAM_RESTART_AFTER_VIDEO") != "":
    STREAM_RESTART_AFTER_VIDEO = default_ini.get(
        "VideoOptions", "STREAM_RESTART_AFTER_VIDEO"
    )
    if not os.path.isabs(STREAM_RESTART_AFTER_VIDEO):
        STREAM_RESTART_AFTER_VIDEO = os.path.join(BASE_PATH, STREAM_RESTART_AFTER_VIDEO)

else:
    STREAM_RESTART_AFTER_VIDEO = None

if default_ini.has_option("VideoOptions", "STREAM_WAIT_AFTER_RETRY"):  # Added in 2.2.0.
    STREAM_WAIT_AFTER_RETRY = default_ini.getint(
        "VideoOptions", "STREAM_WAIT_AFTER_RETRY"
    )
else:
    STREAM_WAIT_AFTER_RETRY = 15

STOP_AFTER_LAST_VIDEO = default_ini.getboolean("VideoOptions", "STOP_AFTER_LAST_VIDEO")

TIME_RECORD_INTERVAL = default_ini.getint("PlayIndex", "TIME_RECORD_INTERVAL")
REWIND_LENGTH = default_ini.getint("PlayIndex", "REWIND_LENGTH")

if default_ini.has_option("Schedule", "SCHEDULE_MIN_VIDEOS"):  # Added in 2.1.0.
    SCHEDULE_MIN_VIDEOS = (
        default_ini.getint("Schedule", "SCHEDULE_MIN_VIDEOS")
        if default_ini.getint("Schedule", "SCHEDULE_MIN_VIDEOS") >= 1
        else 1
    )
else:
    SCHEDULE_MIN_VIDEOS = 1
SCHEDULE_MAX_VIDEOS = (
    default_ini.getint("Schedule", "SCHEDULE_MAX_VIDEOS")
    if default_ini.getint("Schedule", "SCHEDULE_MAX_VIDEOS") >= 1
    else 1
)
SCHEDULE_UPCOMING_LENGTH = (
    default_ini.getint("Schedule", "SCHEDULE_UPCOMING_LENGTH") * 60
)
if default_ini.has_option(
    "Schedule", "SCHEDULE_PREVIOUS_MIN_VIDEOS"
):  # Added in 2.1.0.
    SCHEDULE_PREVIOUS_MIN_VIDEOS = default_ini.getint(
        "Schedule", "SCHEDULE_PREVIOUS_MIN_VIDEOS"
    )
else:
    SCHEDULE_PREVIOUS_MIN_VIDEOS = 1
SCHEDULE_PREVIOUS_MAX_VIDEOS = default_ini.getint(
    "Schedule", "SCHEDULE_PREVIOUS_MAX_VIDEOS"
)
SCHEDULE_PREVIOUS_LENGTH = (
    default_ini.getint("Schedule", "SCHEDULE_PREVIOUS_LENGTH") * 60
)
if default_ini.has_option(
    "Schedule", "SCHEDULE_PREVIOUS_PRUNE_TIGHT"
):  # Added in 2.2.0.
    SCHEDULE_PREVIOUS_PRUNE_TIGHT = default_ini.getboolean(
        "Schedule", "SCHEDULE_PREVIOUS_PRUNE_TIGHT"
    )
else:
    SCHEDULE_PREVIOUS_PRUNE_TIGHT = False
if default_ini.has_option("Schedule", "SCHEDULE_OFFSET"):  # Added in 2.1.0.
    SCHEDULE_OFFSET = default_ini.getint("Schedule", "SCHEDULE_OFFSET")
else:
    SCHEDULE_OFFSET = 0

if default_ini.get("Schedule", "SCHEDULE_EXCLUDE_FILE_PATTERN") != "":
    SCHEDULE_EXCLUDE_FILE_PATTERN = tuple(
        i.strip().casefold().replace("\\", "/")
        for i in default_ini.get("Schedule", "SCHEDULE_EXCLUDE_FILE_PATTERN").split(",")
    )
else:
    SCHEDULE_EXCLUDE_FILE_PATTERN = None

RETRY_ATTEMPTS = default_ini.getint("Retry", "RETRY_ATTEMPTS")
RETRY_PERIOD = (
    default_ini.getint("Retry", "RETRY_PERIOD")
    if default_ini.getint("Retry", "RETRY_PERIOD") != 0
    else 5
)
EXIT_ON_FILE_NOT_FOUND = default_ini.getboolean("Retry", "EXIT_ON_FILE_NOT_FOUND")

REMOTE_ADDRESS = (
    default_ini.get("SSH", "REMOTE_ADDRESS")
    if default_ini.get("SSH", "REMOTE_ADDRESS") != ""
    else None
)
REMOTE_USERNAME = (
    default_ini.get("SSH", "REMOTE_USERNAME")
    if default_ini.get("SSH", "REMOTE_USERNAME") != ""
    else None
)
REMOTE_PASSWORD = (
    default_ini.get("SSH", "REMOTE_PASSWORD")
    if default_ini.get("SSH", "REMOTE_PASSWORD") != ""
    else None
)
REMOTE_PORT = (
    default_ini.getint("SSH", "REMOTE_PORT")
    if default_ini.getint("SSH", "REMOTE_PORT") != ""
    else 22
)
REMOTE_KEY_FILE = (
    default_ini.get("SSH", "REMOTE_KEY_FILE")
    if default_ini.get("SSH", "REMOTE_KEY_FILE") != ""
    else None
)
REMOTE_KEY_FILE_PASSWORD = (
    default_ini.get("SSH", "REMOTE_KEY_FILE_PASSWORD")
    if default_ini.get("SSH", "REMOTE_KEY_FILE_PASSWORD") != ""
    else None
)
REMOTE_DIRECTORY = (
    default_ini.get("SSH", "REMOTE_DIRECTORY")
    if default_ini.get("SSH", "REMOTE_DIRECTORY") != ""
    else None
)
if default_ini.has_option("SSH", "REMOTE_UPLOAD_ATTEMPTS"):  # Added in 2.1.0.
    REMOTE_UPLOAD_ATTEMPTS = (
        default_ini.getint("SSH", "REMOTE_UPLOAD_ATTEMPTS")
        if default_ini.getint("SSH", "REMOTE_UPLOAD_ATTEMPTS") != 0
        else 1
    )
else:
    REMOTE_UPLOAD_ATTEMPTS = 1

# Deprecated in 2.2.0.
# if default_ini.has_option("SSH", "REMOTE_RETRY_PERIOD"):  # Added in 2.1.0.
#     REMOTE_RETRY_PERIOD = (
#         default_ini.getint("SSH", "REMOTE_RETRY_PERIOD")
#         if default_ini.getint("SSH", "REMOTE_RETRY_PERIOD") != 0
#         else 5
#     )
# else:
#     REMOTE_RETRY_PERIOD = 5

# Mail options added in 2.2.0.
if default_ini.has_section("Mail"):
    MAIL_ENABLE = default_ini.getboolean("Mail", "MAIL_ENABLE")
    MAIL_ENV_CONFIG = default_ini.getboolean("Mail", "MAIL_ENV_CONFIG")
    MAIL_ENV_PREFIX = default_ini.get("Mail", "MAIL_ENV_PREFIX")
    if MAIL_ENV_CONFIG:
        MAIL_USE_SSL = os.getenv(f"{MAIL_ENV_PREFIX}MAIL_USE_SSL", "0")
        MAIL_USE_STARTTLS = os.getenv(f"{MAIL_ENV_PREFIX}MAIL_USE_STARTTLS", "0")
        MAIL_SERVER = os.getenv(f"{MAIL_ENV_PREFIX}MAIL_SERVER")
        MAIL_PORT = os.getenv(f"{MAIL_ENV_PREFIX}MAIL_PORT", "0")
        MAIL_LOGIN = os.getenv(f"{MAIL_ENV_PREFIX}MAIL_LOGIN")
        MAIL_PASSWORD = os.getenv(f"{MAIL_ENV_PREFIX}MAIL_PASSWORD")
        MAIL_FROM_ADDRESS = os.getenv(f"{MAIL_ENV_PREFIX}MAIL_FROM_ADDRESS")
        MAIL_TO_ADDRESS = os.getenv(f"{MAIL_ENV_PREFIX}MAIL_TO_ADDRESS")
    else:
        MAIL_USE_SSL = default_ini.getboolean("Mail", "MAIL_USE_SSL")
        MAIL_USE_STARTTLS = default_ini.getboolean("Mail", "MAIL_USE_STARTTLS")
        MAIL_SERVER = default_ini.get("Mail", "MAIL_SERVER")
        MAIL_PORT = default_ini.getint("Mail", "MAIL_PORT")
        MAIL_LOGIN = default_ini.get("Mail", "MAIL_LOGIN", raw=True)
        MAIL_PASSWORD = default_ini.get("Mail", "MAIL_PASSWORD", raw=True)
        MAIL_FROM_ADDRESS = default_ini.get("Mail", "MAIL_FROM_ADDRESS")
        MAIL_TO_ADDRESS = default_ini.get("Mail", "MAIL_TO_ADDRESS")
    MAIL_PROGRAM_NAME = (
        default_ini.get("Mail", "MAIL_PROGRAM_NAME")
        if default_ini.get("Mail", "MAIL_PROGRAM_NAME") != ""
        else "Mr. OTCS"
    )
    MAIL_ALERT_ON_STREAM_DOWN = default_ini.getboolean(
        "Mail", "MAIL_ALERT_ON_STREAM_DOWN"
    )
    MAIL_ALERT_ON_STREAM_RESUME = default_ini.getboolean(
        "Mail", "MAIL_ALERT_ON_STREAM_RESUME"
    )
    MAIL_ALERT_ON_PROGRAM_ERROR = default_ini.getboolean(
        "Mail", "MAIL_ALERT_ON_PROGRAM_ERROR"
    )
    MAIL_ALERT_ON_REMOTE_ERROR = default_ini.getboolean(
        "Mail", "MAIL_ALERT_ON_REMOTE_ERROR"
    )
    MAIL_ALERT_MAX_ERRORS_REPORTED = max(
        default_ini.getint("Mail", "MAIL_ALERT_MAX_ERRORS_REPORTED"), 1
    )
    MAIL_ALERT_ON_COMMAND = default_ini.getboolean("Mail", "MAIL_ALERT_ON_COMMAND")
    MAIL_ALERT_ON_PLAYLIST_LOOP = default_ini.getboolean(
        "Mail", "MAIL_ALERT_ON_PLAYLIST_LOOP"
    )
    MAIL_ALERT_ON_PLAYLIST_STOP = default_ini.getboolean(
        "Mail", "MAIL_ALERT_ON_PLAYLIST_STOP"
    )
    MAIL_ALERT_ON_PLAYLIST_END = default_ini.getboolean(
        "Mail", "MAIL_ALERT_ON_PLAYLIST_END"
    )
    MAIL_ALERT_ON_NEW_VERSION = default_ini.getboolean(
        "Mail", "MAIL_ALERT_ON_NEW_VERSION"
    )
    MAIL_ALERT_ON_NEW_PRERELEASE_VERSION = default_ini.getboolean(
        "Mail", "MAIL_ALERT_ON_NEW_PRERELEASE_VERSION"
    )
    MAIL_ALERT_STATUS_REPORT = default_ini.getint("Mail", "MAIL_ALERT_STATUS_REPORT")
else:
    MAIL_ENABLE = False
    MAIL_ENV_CONFIG = False
    MAIL_ENV_PREFIX = ""
    MAIL_USE_SSL = False
    MAIL_USE_STARTTLS = False
    MAIL_SERVER = ""
    MAIL_PORT = 0
    MAIL_LOGIN = ""
    MAIL_PASSWORD = ""
    MAIL_FROM_ADDRESS = ""
    MAIL_TO_ADDRESS = ""
    MAIL_PROGRAM_NAME = ""
    MAIL_ALERT_ON_STREAM_DOWN = False
    MAIL_ALERT_ON_STREAM_RESUME = False
    MAIL_ALERT_ON_PROGRAM_ERROR = False
    MAIL_ALERT_ON_REMOTE_ERROR = False
    MAIL_ALERT_MAX_ERRORS_REPORTED = 1
    MAIL_ALERT_ON_COMMAND = False
    MAIL_ALERT_ON_PLAYLIST_LOOP = False
    MAIL_ALERT_ON_PLAYLIST_STOP = False
    MAIL_ALERT_ON_PLAYLIST_END = False
    MAIL_ALERT_ON_NEW_VERSION = False
    MAIL_ALERT_ON_NEW_PRERELEASE_VERSION = False

PLAY_HISTORY_LENGTH = default_ini.getint("Misc", "PLAY_HISTORY_LENGTH")
VERBOSE = default_ini.get("Misc", "VERBOSE").lower()

if VERBOSE == "silent":
    VERBOSE = 0
elif VERBOSE == "fatal":
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
    print('VERBOSE setting not recognized. Using default setting "info".')
    VERBOSE = 0b11111100

if default_ini.has_option("Misc", "STREAM_MANUAL_RESTART_DELAY"):  # Added in 2.2.0.
    STREAM_MANUAL_RESTART_DELAY = default_ini.getint(
        "Misc", "STREAM_MANUAL_RESTART_DELAY"
    )
else:
    STREAM_MANUAL_RESTART_DELAY = 5

if default_ini.has_option("Misc", "VERSION_CHECK_INTERVAL"):  # Added in 2.2.0.
    VERSION_CHECK_INTERVAL = default_ini.get("Misc", "VERSION_CHECK_INTERVAL").lower()
    if VERSION_CHECK_INTERVAL == "off":
        VERSION_CHECK_INTERVAL = None
    elif VERSION_CHECK_INTERVAL == "monthly":
        VERSION_CHECK_INTERVAL = 30
    elif VERSION_CHECK_INTERVAL == "biweekly":
        VERSION_CHECK_INTERVAL = 14
    elif VERSION_CHECK_INTERVAL == "weekly":
        VERSION_CHECK_INTERVAL = 7
    elif VERSION_CHECK_INTERVAL == "daily":
        VERSION_CHECK_INTERVAL = 1
    else:
        print(
            'VERSION_CHECK_INTERVAL setting not recognized. Using default setting "monthly".'
        )
        VERSION_CHECK_INTERVAL = 30
else:
    VERSION_CHECK_INTERVAL = 30


def print2(level: str, message: str):
    """Prepend a colored label to a standard print message.
    Also writes messages with severity `warn` or higher to
    log file.
    """

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_log = ""

    reset = "\033[0m"
    notice = "\033[96m" + "[Notice]" + reset
    warn = "\033[93m" + "[Warn]" + reset
    error = "\033[31m" + "[Error]" + reset
    play = "\033[92m" + "[Play]" + reset

    if level == "fatal" and VERBOSE & 0b10000000:
        print(f"{current_time} {error} {message}")
        write_log = f"{current_time} [Error] {message}\n"
    elif level == "error" and VERBOSE & 0b1000000:
        print(f"{current_time} {error} {message}")
        write_log = f"{current_time} [Error] {message}\n"
    elif level == "warn" and VERBOSE & 0b100000:
        print(f"{current_time} {warn} {message}")
        write_log = f"{current_time} [Warn] {message}\n"
    elif level == "notice" and VERBOSE & 0b10000:
        print(f"{current_time} {notice} {message}")
    elif level == "play" and VERBOSE & 0b1000:
        print(f"{current_time} {play} {message}")
    elif level == "info" and VERBOSE & 0b100:
        print(f"{current_time} [Info] {message}")
    elif level == "verbose" and VERBOSE & 0b10:
        print(f"{current_time} [Info] {message}")
    elif level == "verbose2" and VERBOSE & 0b1:
        print(f"{current_time} [Info] {message}")

    if ERROR_LOG is not None and write_log != "":
        with open(ERROR_LOG, "a", encoding="utf-8") as log_file:
            log_file.write(write_log)


# Basic validation of config file structure.
for section, options_dict in ini_defaults.items():
    if default_ini.has_section(section):
        for option in options_dict:
            if not default_ini.has_option(section, option):
                print2(
                    "warn",
                    f"{config_file} is missing option {option} in [{section}] section. Using default value.",
                )
                break
        else:
            continue
    else:
        print2(
            "warn",
            f"{config_file} is missing [{section}] section. Using default values.",
        )
        config_file = os.getenv("MR_OTCS_CONFIG_INI", "config.ini")
        default_ini.read("config.ini")
        break

# Validate config settings.
if ALT_NAMES_JSON_PATH is not None:
    try:
        with open(ALT_NAMES_JSON_PATH, "r", encoding="utf8") as alt_names_json:
            try:
                ALT_NAMES = json.load(alt_names_json)
                print2(
                    "info", f"{len(ALT_NAMES)} keys loaded from {ALT_NAMES_JSON_PATH}."
                )
            except json.JSONDecodeError as e:
                print(e)
                print2(
                    "error",
                    f"Error loading {ALT_NAMES_JSON_PATH} in ALT_NAMES_JSON_PATH.",
                )
                ALT_NAMES = {}

    except FileNotFoundError:
        print2("error", f"{ALT_NAMES_JSON_PATH} in ALT_NAMES_JSON_PATH not found.")
        ALT_NAMES_JSON_PATH = None
        ALT_NAMES = {}
else:
    ALT_NAMES = {}

if CHECK_URL == [""]:
    CHECK_URL = None

# STREAM_RESTART_BEFORE_VIDEO and STREAM_RESTART_AFTER_VIDEO are only checked
# as existing once at startup.
if STREAM_RESTART_BEFORE_VIDEO is not None:
    if not os.path.isfile(STREAM_RESTART_BEFORE_VIDEO):
        print2("error", "STREAM_RESTART_BEFORE_VIDEO not found.")
        if not EXIT_ON_FILE_NOT_FOUND:
            STREAM_RESTART_BEFORE_VIDEO = None
        else:
            sys.exit(1)
else:
    STREAM_RESTART_BEFORE_VIDEO = None

if STREAM_RESTART_AFTER_VIDEO is not None:
    if not os.path.isfile(STREAM_RESTART_AFTER_VIDEO):
        print2("error", "STREAM_RESTART_AFTER_VIDEO not found.")
        if not EXIT_ON_FILE_NOT_FOUND:
            STREAM_RESTART_AFTER_VIDEO = None
        else:
            sys.exit(1)
else:
    STREAM_RESTART_AFTER_VIDEO = None

if REMOTE_ADDRESS is not None and REMOTE_USERNAME is None:
    print2("error", "REMOTE_ADDRESS was specified, but REMOTE_USERNAME is blank.")
    sys.exit(1)

# Enforce a minimum CHECK_INTERVAL time of the number of links provided in
# CHECK_URL times 5 seconds, and no less than 10 seconds for safety.
if CHECK_URL is not None:
    if CHECK_INTERVAL < (len(CHECK_URL) * 5):
        CHECK_INTERVAL = len(CHECK_URL) * 5
    if CHECK_INTERVAL < 10:
        CHECK_INTERVAL = 10

if SCHEDULE_MAX_VIDEOS < SCHEDULE_MIN_VIDEOS:
    print2("error", "SCHEDULE_MAX_VIDEOS is less than SCHEDULE_MIN_VIDEOS.")
    sys.exit(1)

if SCHEDULE_PREVIOUS_MAX_VIDEOS < SCHEDULE_PREVIOUS_MIN_VIDEOS:
    print2(
        "error",
        "SCHEDULE_PREVIOUS_MAX_VIDEOS is less than SCHEDULE_PREVIOUS_MIN_VIDEOS.",
    )
    sys.exit(1)

if MAIL_ENABLE:
    mail_config_error = False

    if MAIL_ENV_CONFIG:
        try:
            MAIL_PORT = int(MAIL_PORT)
            if not (0 < MAIL_PORT <= 65535):
                raise ValueError
        except ValueError:
            print2(
                "error",
                f"Environment variable {MAIL_ENV_PREFIX}MAIL_PORT is not a valid port number.",
            )
            mail_config_error = True

        for i in ["MAIL_USE_SSL", "MAIL_USE_STARTTLS"]:
            try:
                globals()[i] = bool(int(globals()[i]))
            except ValueError:
                print2(
                    "error", f"Environment variable {MAIL_ENV_PREFIX}{i} is invalid."
                )
                mail_config_error = True

        if MAIL_USE_SSL and MAIL_USE_STARTTLS:
            print2(
                "error",
                f"Environment variables {MAIL_ENV_PREFIX}MAIL_USE_SSL and {MAIL_ENV_PREFIX}MAIL_USE_STARTTLS cannot both be enabled.",
            )
            mail_config_error = True

        if MAIL_SERVER is None or MAIL_SERVER == "":
            print2(
                "error", f"Environment variable {MAIL_ENV_PREFIX}MAIL_SERVER is blank."
            )
            mail_config_error = True

        if MAIL_FROM_ADDRESS is None or MAIL_FROM_ADDRESS == "":
            print2(
                "error",
                f"Environment variable {MAIL_ENV_PREFIX}MAIL_FROM_ADDRESS is blank.",
            )
            mail_config_error = True

        if MAIL_TO_ADDRESS is None or MAIL_TO_ADDRESS == "":
            print2(
                "error",
                f"Environment variable {MAIL_ENV_PREFIX}MAIL_TO_ADDRESS is blank.",
            )
            mail_config_error = True
    else:
        if not (0 < MAIL_PORT <= 65535):
            print2("error", "MAIL_PORT is not a valid port number.")
            mail_config_error = True

        if MAIL_USE_SSL and MAIL_USE_STARTTLS:
            print2(
                "error", "MAIL_USE_SSL and MAIL_USE_STARTTLS cannot both be enabled."
            )
            mail_config_error = True

        if MAIL_SERVER is None or MAIL_SERVER == "":
            print2("error", "MAIL_SERVER is blank.")
            mail_config_error = True

        if MAIL_FROM_ADDRESS is None or MAIL_FROM_ADDRESS == "":
            print2("error", "MAIL_FROM_ADDRESS is blank.")
            mail_config_error = True

        if MAIL_TO_ADDRESS is None or MAIL_TO_ADDRESS == "":
            print2("error", "MAIL_TO_ADDRESS is blank.")
            mail_config_error = True

    if mail_config_error:
        sys.exit(1)

# Deprecated options.
if default_ini.has_option("SSH", "REMOTE_RETRY_PERIOD"):
    print2(
        "info",
        f"[Mail] option REMOTE_RETRY_PERIOD has been deprecated and can be deleted from {config_file}.",
    )


if __name__ == "__main__":
    print("Run python3 main.py to start this program.")
