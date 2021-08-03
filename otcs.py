#######################################################################
# Mr. OTCS
#
# https://github.com/TheOpponent/mr-otcs
# https://twitter.com/The_Opponent

import datetime
import errno
import itertools
import json
import os
import subprocess
import sys
import time
from collections import deque
from configparser import ConfigParser
from multiprocessing import Process

config_defaults = {
    "Paths":{
        "MEDIA_PLAYER_PATH":"/usr/local/bin/ffmpeg",
        "FFPROBE_PATH":"/usr/local/bin/ffprobe",
        "BASE_PATH":"/media/videos/",
        "MEDIA_PLAYLIST":"playlist.txt",
        "PLAY_INDEX_FILE":"%(BASE_PATH)s/play_index.txt",
        "PLAY_HISTORY_FILE":"%(BASE_PATH)s/play_history.txt",
        "SCHEDULE_PATH":"schedule.json"
        },
    "VideoOptions":{
        "VIDEO_PADDING":2,
        "MEDIA_PLAYER_BEFORE_ARGUMENTS":
            "-hide_banner -re -ss {elapsed_time} -i",
        "MEDIA_PLAYER_AFTER_ARGUMENTS":
            "-filter_complex \"[0:v]scale=1280x720,fps=30[scaled];"\
            "[scaled]tpad=stop_duration=%(VIDEO_PADDING)s;"\
            "apad=pad_dur=%(VIDEO_PADDING)s\" -c:v h264_omx -b:v 4000k"\
            "-acodec aac -b:a 192k -f flv -g 60 rtmp://localhost:1935/live/"
        },
    "PlayIndex":{
        "TIME_RECORD_INTERVAL":30,
        "REWIND_LENGTH":30,
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
    "Misc":{
        "PLAY_HISTORY_LENGTH":10
        }
    }

config = ConfigParser(defaults=config_defaults)
if len(sys.argv) > 1:
    config.read(["config.ini",sys.argv[1]])
else:
    config.read("config.ini")

MEDIA_PLAYER_PATH = config.get("Paths","MEDIA_PLAYER_PATH")
FFPROBE_PATH = config.get("Paths","FFPROBE_PATH")
BASE_PATH = os.path.expanduser(config.get("Paths","BASE_PATH"))
PLAY_INDEX_FILE = os.path.expanduser(config.get("Paths","PLAY_INDEX_FILE"))
if config.get("Paths","PLAY_HISTORY_FILE") != "":
    PLAY_HISTORY_FILE = os.path.expanduser(config.get("Paths",
                                                      "PLAY_HISTORY_FILE"))
else:
    PLAY_HISTORY_FILE = None

if config.get("Paths","SCHEDULE_PATH") != "":
    SCHEDULE_PATH = os.path.expanduser(config.get("Paths","SCHEDULE_PATH"))
else:
    SCHEDULE_PATH = None

MEDIA_PLAYLIST =  os.path.expanduser(config.get("Paths","MEDIA_PLAYLIST"))

MEDIA_PLAYER_BEFORE_ARGUMENTS = config.get("VideoOptions",
                                           "MEDIA_PLAYER_BEFORE_ARGUMENTS")
MEDIA_PLAYER_AFTER_ARGUMENTS = config.get("VideoOptions",
                                          "MEDIA_PLAYER_AFTER_ARGUMENTS")
VIDEO_PADDING = config.getint("VideoOptions","VIDEO_PADDING")

TIME_RECORD_INTERVAL = config.getint("PlayIndex","TIME_RECORD_INTERVAL")
REWIND_LENGTH = config.getint("PlayIndex","REWIND_LENGTH")

SCHEDULE_MAX_VIDEOS = config.getint("Schedule","SCHEDULE_MAX_VIDEOS")
SCHEDULE_UPCOMING_LENGTH = config.getint("Schedule",
                                         "SCHEDULE_UPCOMING_LENGTH")
SCHEDULE_PREVIOUS_MAX_VIDEOS = config.getint("Schedule",
                                             "SCHEDULE_PREVIOUS_MAX_VIDEOS")
SCHEDULE_PREVIOUS_LENGTH = config.getint("Schedule",
                                         "SCHEDULE_PREVIOUS_LENGTH")


if config.get("Schedule","SCHEDULE_EXCLUDE_FILE_PATTERN") != "":
    SCHEDULE_EXCLUDE_FILE_PATTERN = tuple([i.strip().casefold()
                                        .replace("\\","/")
                                        for i in config.get("Schedule",
                                        "SCHEDULE_EXCLUDE_FILE_PATTERN")
                                        .split(",")])
else:
    SCHEDULE_EXCLUDE_FILE_PATTERN = None

RETRY_ATTEMPTS = config.getint("Retry","RETRY_ATTEMPTS")
RETRY_PERIOD = config.getint("Retry","RETRY_PERIOD")
EXIT_ON_FILE_NOT_FOUND = config.getboolean("Retry","EXIT_ON_FILE_NOT_FOUND")

PLAY_HISTORY_LENGTH = config.getint("Misc","PLAY_HISTORY_LENGTH")


def check_file(path,no_exit=False):
    """Retry opening nonexistent files up to RETRY_ATTEMPTS.
    If file is found, returns True.
    If EXIT_ON_FILE_NOT_FOUND is True, throw exception if retry
    attempts don't succeed. If False, return False and continue.
    no_exit overrides EXIT_ON_FILE_NOT_FOUND.
    """

    retry_attempts_remaining = RETRY_ATTEMPTS

    # If RETRY_ATTEMPTS is -1, don't print number of attempts
    # remaining.
    if retry_attempts_remaining < 0:
        retry_attempts_string = ""

    while not os.path.isfile(path):
        # Print number of attempts remaining.
        if retry_attempts_remaining > 0:
            if retry_attempts_remaining > 1:
                retry_attempts_string = (
                    f"{retry_attempts_remaining} "
                    "attempts remaining."
                    )

            else:
                retry_attempts_string = "1 attempt remaining."
            retry_attempts_remaining -= 1

        elif retry_attempts_remaining == 0:
            if EXIT_ON_FILE_NOT_FOUND and not no_exit:
                raise (
                    FileNotFoundError(errno.ENOENT,
                    os.strerror(errno.ENOENT),path)
                    )

            else:
                print(f"{path} not found. Continuing.")
                return False

        print(
            f"File not found: {path}.\n"
            f"{retry_attempts_string} "
            f"Retrying in {RETRY_PERIOD} seconds..."
            )

        time.sleep(RETRY_PERIOD)

    else:
        return True


def get_extra_info(entry):
    """Split entry string at delimiter : and return a 2-element list.
    First element is tuple containing a filename split by extension.
    If the delimiter is not found, second element returned is an empty
    string.
    """
    entry = entry.split(" :",1)
    # Split filename by extension.
    entry[0] = os.path.splitext(entry[0].replace("\\","/"))
    if len(entry) > 1:
        return entry
    else:
        return [entry[0],""]


def get_length(file):
    """Run ffprobe and retrieve length of file."""

    result = subprocess.run([
        FFPROBE_PATH,
        "-v","error",
        "-select_streams","v:0",
        "-show_entries","stream=duration",
        "-of","default=noprint_wrappers=1:nokey=1",
        file
        ],
        capture_output=True,text=True).stdout

    if result == "":
        raise Exception("ffprobe was unable to read duration of: " + file)

    return int(float(result))


def write_schedule(file_list,index,str_pattern,time_rewind=0):
    """
    Write a JSON file containing file names and lengths read from a
    list containing video file paths. Optionally, include the most
    recently played file as well.
    """

    def get_next_file(list_sub,index_sub):
        """Get next file from list, looping the list around when it
        runs out.
        """

        list_iter = (i for i in list_sub[index_sub:])

        while True:
            try:
                yield next(list_iter)
            # Produce cycled list when generator runs out.
            except StopIteration:
                list_iter = itertools.cycle(list_sub)

    def get_prev_file(list_sub,index_sub):
        """Get previous file from list, looping the list around when it
        runs out. This is done by slicing the list passed in, then
        reversing the original and sliced lists.
        """

        list_sub_reverse = list_sub[:index_sub]
        list_sub_reverse.reverse()
        list_sub.reverse()
        list_iter = (i for i in list_sub_reverse)

        while True:
            try:
                yield next(list_iter)
            # Produce cycled list when generator runs out.
            except StopIteration:
                list_iter = itertools.cycle(list_sub)

    def create_entry(element,type="normal",time=""):
        """Return a dictionary for JSON based on information
        parsed from string element in list.
        If type is "normal", element should be a 2-element list
        split by get_extra_info().
        """

        if type == "normal":
            return {
                "type":"normal",
                "name":element[0][0],
                "time":time,
                "extra_info":element[1]
                }

        elif type == "extra":
            return {
                "type":"extra",
                "name":"",
                "time":"",
                "extra_info":element[1:]
                }

    def process_filename(filename):
        """Process a filename for insertion. Returns either a
        two-element list from get_extra_info() with a changed title
        from alt_names, or None for entries to be passed over.
        """

        nonlocal duration, total_duration, alt_names

        filename = get_extra_info(filename)

        # Check file, and if entry cannot be found, skip the entry.
        if not check_file(os.path.join(BASE_PATH,''.join(filename[0])),
            no_exit=True):

            return None

        # Get length of video in seconds from ffprobe, plus
        # ffmpeg padding.
        duration += (get_length(os.path.join(BASE_PATH,''.join(filename[0])))
                     + VIDEO_PADDING)
        total_duration += duration

        # Skip files matching SCHEDULE_EXCLUDE_FILE_PATTERN, but keep
        # their durations.
        if (str_pattern is not None and
            filename[0][0].casefold().startswith(str_pattern)):

            return None

        # Read the alt_names dictionary. If filename has a matching
        # key, replace the name with the value.
        if alt_names is not None:
            if filename[0][0] in alt_names:
                if isinstance(alt_names[filename[0][0]],str):
                    filename[0] = (alt_names[filename[0][0]],filename[0][1])
                else:
                    print(f"""Alternate name for {filename[0][0]} in
                        alt_names.json is not a valid string.""")

        return filename

    # Load alt_names.json.
    try:
        with open("alt_names.json","r") as alt_names_json:
            alt_names = json.load(alt_names_json)
    except:
        alt_names = None

    # Get names and start times of upcoming videos.

    # For the first file in file_list, this is the current system time.
    # Time is retrieved in UTC, to be converted to user's local time
    # when they load the schedule in their browser.
    next_time = datetime.datetime.utcnow()

    # Offset first program timing by elapsed_time read in the
    # second line of play_index.txt.
    duration = -time_rewind
    total_duration = -time_rewind

    coming_up_next = deque()

    for filename in get_next_file(file_list,index):

        # Break when either limit is reached.
        if (len([i for i in coming_up_next if i["type"] == "normal"])
            > SCHEDULE_MAX_VIDEOS or
            total_duration > (SCHEDULE_UPCOMING_LENGTH * 60)):

            break

        # Skip comment lines.
        if filename is None:
            continue

        # Add extra lines and continue.
        if filename.startswith(":"):
            coming_up_next.append(create_entry(filename,type="extra"))
            continue

        processed_name = process_filename(filename)

        if processed_name is not None:
            coming_up_next.append(create_entry(processed_name,
                                time=next_time.strftime("%Y-%m-%d %H:%M:%S")))
        else:
            continue

        # Add length of current video to current time and use as
        # starting time for next video.
        next_time += datetime.timedelta(seconds=duration)
        duration = 0

    # Get names and start times of previous videos.
    # Process is similar to adding upcoming videos but some steps
    # run in opposite order.
    # If time_rewind is not 0 because of a resume, do not provide
    # previous file information, as a stream may have restarted
    # after an unexpected exit.
    if SCHEDULE_PREVIOUS_MAX_VIDEOS > 0 and time_rewind == 0:

        prev_time = datetime.datetime.utcnow()
        duration = 0
        total_duration = 0
        previous_files = deque()

        for filename in get_prev_file(file_list,index):
            if (len([i for i in previous_files if i["type"] == "normal"])
                > SCHEDULE_PREVIOUS_MAX_VIDEOS or
                total_duration > (SCHEDULE_PREVIOUS_LENGTH * 60)):
                break

            if filename is None:
                continue

            if filename.startswith(":"):
                previous_files.appendleft(create_entry(filename,type="extra"))
                continue

            processed_name = process_filename(filename)

            # Subtract duration from current time before appending.
            prev_time -= datetime.timedelta(seconds=duration)

            if processed_name is not None:
                previous_files.appendleft(create_entry(processed_name,
                                time=prev_time.strftime("%Y-%m-%d %H:%M:%S")))
            else:
                continue

            duration = 0

    else:
        previous_files = []

    schedule_json_out = {
        "coming_up_next":list(coming_up_next),
        "previous_files":list(previous_files),
        "script_version":SCRIPT_VERSION
        }

    with open(SCHEDULE_PATH,"w+") as schedule_json:
        schedule_json.write(json.dumps(schedule_json_out))

    # Upload JSON file to a publicly accessible location
    # using pysftp or something similar if necessary here.


def write_index(play_index, elapsed_time):
    """Write play_index and elapsed time to play_index.txt
    at the period set by TIME_RECORD_INTERVAL.
    """

    while True:
        with open(os.path.join(BASE_PATH,"play_index.txt"),"w") as index_file:
            index_file.write(f"{play_index}\n{elapsed_time}")

        elapsed_time += TIME_RECORD_INTERVAL
        time.sleep(TIME_RECORD_INTERVAL)


def main():

    # If MEDIA_PLAYLIST is a file, open the file.
    if isinstance(MEDIA_PLAYLIST,str):
        with open(MEDIA_PLAYLIST,"r",encoding="utf-8-sig") as media_playlist_file:
            media_playlist = media_playlist_file.read().splitlines()

    elif isinstance(MEDIA_PLAYLIST,list):
        media_playlist = MEDIA_PLAYLIST

    else:
        raise Exception("MEDIA_PLAYLIST is not a file or Python list.")

    # Change blank lines and comment entries in media_playlist to None.
    media_playlist = [
        i if i != "" and not i.startswith((";","#","//"))
        else None for i in media_playlist
        ]

    # Set initial exit_time. exit_time is set to elapsed time since
    # playback began and compared to start time stored in video_time in
    # next loop.
    exit_time = datetime.datetime.now()

    while True:
        # Keep playlist index and elapsed time of current video and store
        # in file play_index.txt. Create it if it does not exist.
        play_index_contents = []

        try:
            with open(PLAY_INDEX_FILE,"r") as index_file:
                play_index_contents = index_file.readlines()

        except FileNotFoundError:
            with open(PLAY_INDEX_FILE,"w+") as index_file:

                index_file.write("0\n0")
                play_index = 0
                elapsed_time = 0

        # Reset index to 0 if it overruns the playlist.
        try:
            play_index = int(play_index_contents[0])
            media_playlist[play_index]
        except IndexError:
            play_index = 0

        try:
            elapsed_time = int(play_index_contents[1])
        except IndexError:
            elapsed_time = 0

        # Set an extra_offset equal to the number of extra and
        # comment lines before the next video file entry. This offset
        # is not passed to write_schedule(), allowing for extra lines
        # to be written into the first element of coming_up_next.
        extra_offset = 0

        # Play next video file, unless it is a comment entry.
        # Entries beginning with : are extra lines to be printed into
        # the schedule.
        while (media_playlist[play_index + extra_offset] is None
            or media_playlist[play_index + extra_offset].startswith(":")):

            extra_offset += 1

        video_time = datetime.datetime.now()
        video_file = get_extra_info(
                            media_playlist[play_index + extra_offset])
        video_file_fullpath = os.path.join(BASE_PATH,
                                            ''.join(video_file[0]))

        result = check_file(video_file_fullpath)

        if result:
            # If the second line of play_index.txt is greater than
            # REWIND_LENGTH, pass it to media player arguments.
            if elapsed_time < REWIND_LENGTH:
                elapsed_time = 0
            else:
                # If video took less than REWIND_LENGTH to play
                # (e.g. repeatedly failing to start or first loop
                # of script), do not rewind.
                if (exit_time - video_time).seconds > REWIND_LENGTH:
                    elapsed_time -= REWIND_LENGTH

            # Write history of played video files and timestamps,
            # limited to PLAY_HISTORY_LENGTH.
            if PLAY_HISTORY_FILE is not None:
                try:
                    with open(PLAY_HISTORY_FILE,"r") as play_history:
                        play_history_buffer = play_history.readlines()

                except FileNotFoundError:
                    with open(PLAY_HISTORY_FILE,"w+") as play_history:
                        play_history_buffer = []
                        play_history.close()

                finally:
                    with open(PLAY_HISTORY_FILE,"w+") as play_history:
                        play_history_buffer.append(
                            f"{video_time} - {play_index}. {''.join(video_file[0])}\n")
                        play_history.writelines(
                            play_history_buffer[-PLAY_HISTORY_LENGTH:])

            print("Now playing: " + video_file[0][0])

            schedule_p = Process(target=write_schedule,
                args=(
                    media_playlist,
                    play_index,
                    SCHEDULE_EXCLUDE_FILE_PATTERN,
                    elapsed_time
                    )
                )
            player_p = Process(target=subprocess.run,
                kwargs={
                    "args":f"\"{MEDIA_PLAYER_PATH}\" "
                    f"{MEDIA_PLAYER_BEFORE_ARGUMENTS} "
                    .format(elapsed_time=elapsed_time) +
                    f"\"{video_file_fullpath}\" "
                    f"{MEDIA_PLAYER_AFTER_ARGUMENTS}","shell":True,
                    "check":True
                    }
                )
            write_p = Process(target=write_index,
                args=(play_index,elapsed_time))

            player_p.start()
            if SCHEDULE_PATH is not None:
                schedule_p.start()
            write_p.start()
            player_p.join()
            if schedule_p.is_alive():
                schedule_p.join()
            write_p.terminate()

        exit_time = datetime.datetime.now()

        if player_p.exitcode == 0:
            if play_index < len(media_playlist):
                play_index += 1 + extra_offset

            else:
                # Reset index at end of playlist.
                play_index = 0

            with open(PLAY_INDEX_FILE,"w") as index_file:
                index_file.write(str(play_index) + "\n0")


SCRIPT_VERSION = "1.5.1"

if __name__ == "__main__":
    main()
