# Functions for handling the playlist and schedule files.

import datetime
import errno
import itertools
import json
import os
import subprocess
import sys
import time
from collections import deque
from typing import Generator, Tuple

import config
from headers import *

try:
    import pysftp
except ImportError:
    print(f"{info} pysftp is not installed.")


class PlaylistEntry():
    """Definition for playlist entries, parsed from a list or text file
    containing formatted playlist entry strings.

    A PlaylistEntry can be three types:
    "normal": Contains a path to a video file.
    "extra": A comment to be printed in the schedule page.
    "command": A directive to control the stream.

    The commands currently include:
    %RESTART: Force the stream to play the video defined in
    config.STREAM_RESTART_BEFORE_VIDEO, if any, and then restart.

    When a PlaylistEntry is created, it stores only information based on the
    provided string. Video files may change before they are played, so
    duration and other information is calculated only as it is played.

    self.name will contain a relative path to a file name, or a blank string
    if self.type is not "normal".
    """

    type: str
    "One of 'normal', 'extra', 'command', or 'blank'. Normal entries contain information on a video file."

    name: str
    "For normal entries, the name of this video as displayed in the schedule. This can be overwritten with an alternate name."

    path: str
    "The full path to this video file."

    info: str
    "For normal and extra entries, any metadata attached to this entry. For command entries, the directive to run."

    def __init__(self,entry):

        if entry is None:
            self.type = "blank"
            self.name = None
            self.path = None
            self.info = None
        elif entry.startswith(":"):
            self.type = "extra"
            self.name = None
            self.path = None
            self.info = entry[1:]
        elif entry.startswith("%"):
            self.type = "command"
            self.name = None
            self.path = None
            self.info = entry[1:]
        else:
            self.type = "normal"
            split_name = entry.split(" :",1)
            self.name = os.path.splitext(split_name[0])
            self.path = os.path.join(config.BASE_PATH,''.join(split_name[0]))
            if len(split_name) > 1:
                self.info = split_name[1]
            else:
                self.info = ""


def get_length(video):
    """Run ffprobe and retrieve length of a video file."""

    if video is None:
        return 0

    result = subprocess.run([config.FFPROBE_PATH,"-v","error","-select_streams","v:0","-show_entries","stream=duration","-of","default=noprint_wrappers=1:nokey=1",video],capture_output=True,text=True).stdout

    if result == "":
        raise RuntimeError(f"{error} ffprobe was unable to read duration of: " + video)

    return int(float(result))


def check_file(path,line_num=None,no_exit=False):
    """Retry opening nonexistent files up to RETRY_ATTEMPTS.
    If file is found, returns True.
    If EXIT_ON_FILE_NOT_FOUND is True, throw exception if retry
    attempts don't succeed. If False, return False and continue.
    no_exit overrides EXIT_ON_FILE_NOT_FOUND.
    """

    if path is None:
        return True

    retry_attempts_remaining = config.RETRY_ATTEMPTS

    # If RETRY_ATTEMPTS is -1, don't print number of attempts
    # remaining.
    if retry_attempts_remaining < 0:
        retry_attempts_string = ""

    while not os.path.isfile(path):
        # Print number of attempts remaining.
        if retry_attempts_remaining > 0:
            if retry_attempts_remaining > 1:
                retry_attempts_string = (f"{info} {retry_attempts_remaining} attempts remaining.")
            else:
                retry_attempts_string = f"{info} 1 attempt remaining."
            retry_attempts_remaining -= 1

        elif retry_attempts_remaining == 0:
            if config.EXIT_ON_FILE_NOT_FOUND and not no_exit:
                print(f"{error} Line {line_num}: {path} not found." if line_num is not None else f"{error} {path} not found.")
                raise FileNotFoundError(errno.ENOENT,os.strerror(errno.ENOENT),path)
            else:
                print(f"{error} Line {line_num}: {path} not found. Continuing." if line_num is not None else f"{error} {path} not found. Continuing.")
                return False

        print(
            f"{error} File not found: {path}.\n"
            f"{warn} {retry_attempts_string} "
            f"{warn} Retrying in {config.RETRY_PERIOD} seconds..."
            )

        time.sleep(config.RETRY_PERIOD)

    else:
        return True


def create_playlist() -> list[Tuple[int,PlaylistEntry]]:
    """
    Read config.MEDIA_PLAYLIST, which is set to either a text file or a
    list, containing a sequence of playlist entries.

    Returns an enumerated list containing either PlaylistEntry objects
    or None.
    """

    playlist = []

    # If config.MEDIA_PLAYLIST is a file, open the file.
    if isinstance(config.MEDIA_PLAYLIST,str):
        try:
            with open(config.MEDIA_PLAYLIST,"r",encoding="utf-8-sig") as media_playlist_file:
                media_playlist = media_playlist_file.read().splitlines()
        except FileNotFoundError:
            print(f"{error} Playlist file {config.MEDIA_PLAYLIST} not found.")
            exit(1)

    elif isinstance(config.MEDIA_PLAYLIST,list):
        media_playlist = config.MEDIA_PLAYLIST

    else:
        raise TypeError(f"{error} MEDIA_PLAYLIST is not a file or Python list.")

    # Change blank lines and comment entries in media_playlist to None.
    media_playlist = [i if i != "" and not i.startswith((";","#","//")) else None for i in media_playlist]

    # Create an enumerated list of playlist entries, starting at 1,
    # corresponding to line numbers in the playlist text file.
    # Blank lines and comments will be None.
    index = 1
    entry_count = 0
    for i in media_playlist:
        entry_count += 1
        new_entry = PlaylistEntry(i)

        # Read the ALT_NAMES dictionary. If filename has a matching
        # key, replace the name with the value.
        if new_entry.name[0] in config.ALT_NAMES:
            if isinstance(config.ALT_NAMES[new_entry.name],str):
                new_entry.name = config.ALT_NAMES[new_entry.name[0]]
            else:
                print(f"{warn} Alternate name for {new_entry.name} in alt_names.json is not a valid string.")
        else:
            new_entry.name = new_entry.name[0]

        if config.VERBOSE:
            if i is not None:
                print(f"[Info] Adding entry: {index}. {new_entry.name}")
            else:
                print(f"[Info] Adding entry: {index}. (Comment line)")
        playlist.append((index,new_entry))

        index += 1

    if entry_count == 0:
        print(f"{error} No valid entries found in {config.MEDIA_PLAYLIST}.")
        exit(1)

    return playlist


def get_stream_restart_duration():
    """Helper function to add combined duration of
    config.STREAM_RESTART_BEFORE_VIDEO,
    config.STREAM_RESTART_AFTER_VIDEO,
    and config.STREAM_RESTART_WAIT.
    """

    duration = 0

    if config.STREAM_RESTART_BEFORE_VIDEO is not None and check_file(config.STREAM_RESTART_BEFORE_VIDEO,line_num=-1,no_exit=True):
        duration += get_length(config.STREAM_RESTART_BEFORE_VIDEO) + config.VIDEO_PADDING
    if config.STREAM_RESTART_AFTER_VIDEO is not None and check_file(config.STREAM_RESTART_AFTER_VIDEO,line_num=-2,no_exit=True):
        duration += get_length(config.STREAM_RESTART_AFTER_VIDEO) + config.VIDEO_PADDING
    duration += config.STREAM_RESTART_WAIT

    return duration


# History of previous files is built as the program proceeds through
# the playlist.
recent_playlist = deque()
if config.SCHEDULE_PREVIOUS_MAX_VIDEOS:
    previous_files = deque(maxlen=config.SCHEDULE_PREVIOUS_MAX_VIDEOS)
else:
    previous_files = None


def write_schedule(playlist: list,entry_index: int,first_length_offset: int=0,stream_time_remaining: int=0):
    """Write a JSON file containing file names and lengths read from playlist.
    The playlist, a list created by create_playlist(), is read starting from
    the entry_index.

    File names matching config.SCHEDULE_EXCLUDE_FILE_PATTERN are not included
    in the output, but their durations are calculated and added to the next
    eligible entry.

    first_length_offset is the starting time of the currently playing video,
    if it did not start from the beginning.

    stream_time_remaining is used to predict time-based automatic stream
    restarts. The calculated length of the first video in the sliced
    playlist is subtracted from this amount.

    The JSON file includes the following keys:
    start_time: The time this function was called, which approximates
    to the time the currently playing video file began, in UTC.
    coming_up_next: Nested JSON objects with a combined duration not
    exceeding SCHEDULE_MAX_VIDEOS or SCHEDULE_UPCOMING_LENGTH.
    previous_files: Nested JSON objects popped from a deque containing the
    coming_up_next objects.
    script_version: The current script version.

    The coming_up_next objects have the following keys:
    type: Either "normal" or "extra".
    name: The video name for normal entries, a blank string for extra entries.
    time: Approximate time this video started, in UTC, formatted as a string.
    unixtime: Approximate time this video started as a Unix timestamp.
    length: Length of the video in seconds, including VIDEO_PADDING.
    extra_info: The string from the PlaylistEntry .info attribute.

    Note that the time and unixtime values for objects after the first are
    estimates, due to variances in stream delivery.
    """

    global previous_files, recent_playlist

    def iter_playlist(list_sub,index_sub) -> Generator[Tuple[int,PlaylistEntry],None,None]:
        """Get next file from list, looping the list around when it
        runs out.
        """

        list_iter = (i for i in list_sub[index_sub:])
        list_full_iter = itertools.cycle(list(list_sub))

        while True:
            try:
                yield next(list_iter)
            except StopIteration:
                yield next(list_full_iter)

    # For the first file in playlist, this is the current system time.
    # Time is retrieved in UTC, to be converted to user's local time
    # when they load the schedule in their browser.
    start_time = datetime.datetime.utcnow()
    current_time = datetime.datetime.utcnow()

    # total_duration is the cumulative duration of all videos added so
    # far and is checked against config.SCHEDULE_UPCOMING_LENGTH.
    total_duration = 0

    # coming_up_next is a deque of PlaylistEntry objects starting with the
    # current video up to the amount of videos defined by the limits
    # config.SCHEDULE_MAX_VIDEOS and config.SCHEDULE_UPCOMING_LENGTH.
    # coming_up_next_json is a list containing info extracted from the
    # PlaylistEntry objects.
    coming_up_next = deque()
    coming_up_next_json = []

    length_offset = -first_length_offset

    # First entry is the file playing now and is added unconditionally.
    sub_playlist = iter_playlist(playlist,entry_index)
    entry = next(sub_playlist)
    entry_length = get_length(entry[1].path) + config.VIDEO_PADDING + length_offset
    stream_time_remaining -= entry_length
    if stream_time_remaining <= 0:
        length_offset = get_stream_restart_duration()
        stream_time_remaining = config.STREAM_TIME_BEFORE_RESTART - get_stream_restart_duration()

    coming_up_next_json.append({
        "type":"normal",
        "name":entry[1].name,
        "time":start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "unixtime":start_time.timestamp(),
        "length":entry_length,
        "extra_info":entry[1].info
    })

    total_duration += entry_length

    if stream_time_remaining < total_duration:
        length_offset = get_stream_restart_duration()
        stream_time_remaining = config.STREAM_TIME_BEFORE_RESTART - get_stream_restart_duration()
    else:
        length_offset = 0

    for entry in sub_playlist:

        # Break when either limit is reached.
        if (len([i for i in coming_up_next if i.type == "normal"]) > config.SCHEDULE_MAX_VIDEOS or total_duration > (config.SCHEDULE_UPCOMING_LENGTH * 60)):
            break

        if entry[1].type == "blank":
            continue

        else:
            coming_up_next.append(entry[1])

            # In the event of a stream restart, the value returned by
            # get_stream_restart_duration() is added to length_offset and added
            # to the next normal entry.
            if entry[1].type == "normal":
                entry_length = get_length(entry[1].path) + config.VIDEO_PADDING
                stream_time_remaining -= entry_length + length_offset
                if stream_time_remaining <= 0:
                    length_offset = get_stream_restart_duration()
                    stream_time_remaining = config.STREAM_TIME_BEFORE_RESTART - get_stream_restart_duration()

                current_time = current_time + datetime.timedelta(seconds=entry_length + length_offset)

                coming_up_next_json.append({
                    "type":"normal",
                    "name":entry[1].name,
                    "time":current_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "unixtime":current_time.timestamp(),
                    "length":entry_length,
                    "extra_info":entry[1].info
                })

                total_duration += entry_length + length_offset

                if stream_time_remaining < total_duration:
                    length_offset = get_stream_restart_duration()
                    stream_time_remaining = config.STREAM_TIME_BEFORE_RESTART - get_stream_restart_duration()
                else:
                    length_offset = 0

            elif entry[1].type == "extra":
                coming_up_next_json.append({
                "type":"extra",
                "name":"",
                "time":"",
                "unixtime":0,
                "length":0,
                "extra_info":entry[1].info
                })

            elif entry[1].type == "command":
                if entry[1].info == "RESTART":
                    length_offset = get_stream_restart_duration()
                else:
                    raise ValueError(f"{error} Line {entry[0]}: Playlist directive {entry[1].info} not recognized.")

            else:
                print(f"{warn} Line {entry[0]}: Invalid entry. Skipping.")

    if previous_files is not None:
        prev_total_duration = 0
        # When the program starts, recent_playlist will be empty.
        if len(recent_playlist):
            previous_files.append(recent_playlist.popleft())

            # If combined length of previous_files exceeds SCHEDULE_PREVIOUS_LENGTH,
            # pop left.
            for i in previous_files:
                if i["type"] == "normal":
                    prev_total_duration += i["length"]

            while len(previous_files) > 1 and prev_total_duration > (config.SCHEDULE_PREVIOUS_LENGTH * 60):
                pop = previous_files.popleft()
                prev_total_duration -= pop["length"]

        recent_playlist = deque(coming_up_next_json.copy())

        # Break when either limit is reached.
        # if (len([i for i in coming_up_next if i["type"] == "normal"]) > config.SCHEDULE_MAX_VIDEOS or total_duration > (config.SCHEDULE_UPCOMING_LENGTH * 60)):
        #     break

        # # Skip blank lines.
        # if entry[1].type == "blank":
        #     continue

        # # Add extra lines and continue.
        # if entry[1].type == "extra":
        #     coming_up_next.append({
        #         "type":"extra",
        #         "name":"",
        #         "time":"",
        #         "extra_info":entry[1].info
        #         })
        #     continue

        # elif entry[1].type == "command":
        #     if entry[1].info == "RESTART":
        #         duration += get_stream_restart_duration()
        #     else:
        #         raise ValueError(f"{warn} Line {entry[0]}: Playlist directive {entry[1].info} not recognized.")
        #     continue

        # elif entry[1].type == "normal":
        #     if config.SCHEDULE_EXCLUDE_FILE_PATTERN is not None and entry[1].name.casefold().startswith(config.SCHEDULE_EXCLUDE_FILE_PATTERN):
        #         if config.VERBOSE:
        #             print(f"[Info] Line {entry[0]}: File name {entry[1].name} matches SCHEDULE_EXCLUDE_FILE_PATTERN; not adding to schedule.")
        #         continue
        #     if check_file(entry[1].path,line_num=entry[0]):
        #         duration += get_length(entry[1].path) + config.VIDEO_PADDING
        #         stream_time_remaining -= duration
        #         if stream_time_remaining <= 0:
        #             next_time += datetime.timedelta(seconds=get_stream_restart_duration())
        #             stream_time_remaining = config.STREAM_TIME_BEFORE_RESTART
        #         coming_up_next.append({
        #             "type":"normal",
        #             "name":entry[1].name,
        #             "time":next_time.strftime("%Y-%m-%d %H:%M:%S"),
        #             "extra_info":entry[1].info
        #         })

        # else:
        #     print(f"Line {entry[0]}: Invalid entry.")
        #     continue

        # Add length of current video to current time and use as
        # starting time for next video.
        # next_time += datetime.timedelta(seconds=duration)
        # duration = 0

    # Get names and start times of previous videos.
    # Process is similar to adding upcoming videos but some steps
    # run in opposite order.
    # If time_rewind is not 0 because of a resume, do not provide
    # previous file information, as a stream may have restarted
    # after an unexpected exit.


        # Insert at least one entry from the last coming_up_next
        # deque that was generated last time this function was called.
        # When this program starts, it will be empty.
        # if len(previous_playlist):

        # prev_time = datetime.datetime.utcnow()
        # duration = 0
        # total_duration = 0

    #     for entry in get_prev_file(playlist,entry_index):

    #         if (len([i for i in previous_files if i["type"] == "normal"]) > config.SCHEDULE_PREVIOUS_MAX_VIDEOS or total_duration > (config.SCHEDULE_PREVIOUS_LENGTH * 60)):
    #             break

    #         # Skip comment lines.
    #         if entry[1] is None:
    #             continue

    #         # Add extra lines and continue.
    #         if entry[1].type == "extra":
    #             previous_files.appendleft({
    #                 "type":"extra",
    #                 "name":"",
    #                 "time":"",
    #                 "extra_info":entry[1].info
    #                 })
    #             continue

    #         elif entry[1].type == "command":
    #             if entry[1].info == "RESTART":
    #                 duration += get_stream_restart_duration()
    #             else:
    #                 raise ValueError(f"{error} Line {entry[0]}: Playlist directive {entry[1].info} not recognized.")
    #             continue

    #         elif entry[1].type == "normal":

    #             if check_file(entry[1].path,line_num=entry[0]):
    #                 duration += get_length(entry[1].path) + config.VIDEO_PADDING
    #                 # Subtract duration from current time before appending.
    #                 prev_time -= datetime.timedelta(seconds=duration)
    #                 previous_files.appendleft({
    #                     "type":"normal",
    #                     "name":entry[1].name,
    #                     "time":prev_time.strftime("%Y-%m-%d %H:%M:%S"),
    #                     "extra_info":entry[1].info
    #                 })

    #         duration = 0

    # else:
    #     previous_files = []


    schedule_json_out = {
        "start_time":start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "coming_up_next":list(coming_up_next_json),
        "previous_files":list(previous_files),
        "script_version":config.SCRIPT_VERSION
        }

    with open(config.SCHEDULE_PATH,"w+") as schedule_json:
        schedule_json.write(json.dumps(schedule_json_out))


def upload_sftp():
    """Upload JSON file to a publicly accessible location
    using pysftp, if it is installed.
    """

    if "pysftp" in sys.modules and config.REMOTE_ADDRESS != "":
        with pysftp.Connection(config.REMOTE_ADDRESS,
            username=config.REMOTE_USERNAME,
            private_key=config.REMOTE_KEY_FILE,
            password=config.REMOTE_PASSWORD,
            port=config.REMOTE_PORT,
            private_key_pass=config.REMOTE_KEY_FILE_PASSWORD,
            default_path=config.REMOTE_DIRECTORY) as sftp:

            sftp.put(config.SCHEDULE_PATH)

    else:
        print("pysftp is not installed.")


elapsed_time = 0

def write_index(play_index, video_start_time):
    """Write play_index and elapsed time to play_index.txt
    at the period set by TIME_RECORD_INTERVAL.
    """

    global elapsed_time

    elapsed_time = 0

    while True:
        with open(config.PLAY_INDEX_FILE,"w") as index_file:
            index_file.write(f"{play_index}\n{video_start_time + elapsed_time}")

        elapsed_time += config.TIME_RECORD_INTERVAL
        time.sleep(config.TIME_RECORD_INTERVAL)


if __name__ == "__main__":
    print("Run python3 main.py to start this program.")