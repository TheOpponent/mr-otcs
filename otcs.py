import datetime
import errno
import itertools
import json
import os
import subprocess
import sys
import time
from multiprocessing import Process

#######################################################################
# Paths configuration.
# Windows users need to use two backslashes \\ for paths.

# Program paths. Use absolute paths.
# ffprobe is optional if HTML schedule will not be used.
MEDIA_PLAYER_PATH = "/usr/local/bin/ffmpeg"
FFPROBE_PATH = "/usr/local/bin/ffprobe"

# Base path for all video files, including trailing slash.
# This path will also contain play_index.txt and play_history.txt.
BASE_PATH = "/media/videos/"

# Number of seconds of black video to add between each video.
# This is added to schedule durations for each video.
# Set to 0 if not using ffmpeg.
VIDEO_PADDING = 2

# Arguments to pass to media player. This should be whatever is
# necessary to immediately exit the player after playback is completed.
# MEDIA_PLAYER_BEFORE_ARGUMENTS are passed before the input file.
# MEDIA_PLAYER_AFTER_ARGUMENTS are passed after the input file.
# To save playback position, add "{}" as a parameter for the
# corresponding media player argument to set start time.
MEDIA_PLAYER_BEFORE_ARGUMENTS = "-hide_banner -re -ss {} -i"
MEDIA_PLAYER_AFTER_ARGUMENTS = f"-filter_complex \"[0:v]scale=1280x720,fps=30[scaled];[scaled]tpad=stop_duration={VIDEO_PADDING};apad=pad_dur={VIDEO_PADDING}\" -c:v h264_omx -b:v 4000k -acodec aac -b:a 192k -f flv -g 60 rtmp://localhost:1935/live/"

# Video files, including subdirectories. This can be a Python list
# containing strings with filenames in BASE_PATH or a string with a
# path to a text file containing one filename in BASE_PATH per line.
# Items starting with comment characters ; # or // and blank lines will
# be skipped.
# List example:
# MEDIA_PLAYLIST = ["video1.mp4","video2.mp4","Series/S01E01.mp4"]
MEDIA_PLAYLIST = "/home/pi/playlist.txt"

#######################################################################
# Playback info file configuration.
# To save playback progress, this script saves a file named
# play_index.txt to BASE_PATH.
# The first line contains the index of the playlist starting at 0.
# The second line contains the elapsed time of the current
# video playback in seconds.

# Interval to save playback position in seconds.
# Lower intervals are more precise in resuming when the script is
# unexpectedly terminated, but if BASE_PATH is on flash media like
# USB drive or SD card, higher intervals are recommended to reduce
# disk writes.
TIME_RECORD_INTERVAL = 30

# When resuming video with a saved time in play_index.txt, rewind this
# many seconds. Recommended when streaming to RTMP.
REWIND_LENGTH = 30

#######################################################################
# Schedule configuration.

# Enable JSON schedule generation. Set to False to disable.
SCHEDULE_ENABLE = True

# Number of upcoming shows to write in schedule.
# Set SCHEDULE_UPCOMING_LENGTH to the total number of minutes of
# video to add to the schedule, and SCHEDULE_MAX_VIDEOS to limit
# the number of videos.
SCHEDULE_UPCOMING_LENGTH = 240
SCHEDULE_MAX_VIDEOS = 15

# Filename pattern to exclude in schedules. This can be used to exclude
# categories of videos such as station idents or commercials from the
# schedule. Their durations will still be calculated and added to
# the durations of preceding videos to keep the times aligned.
# Set to a single string or a Python list with strings; paths
# beginning with these strings (case insensitive) will be ignored.
# e.g. ["Station Breaks/","Commercial"] will exclude all files in
# the Station Breaks directory and all files and paths in BASE_PATH
# starting with "Commercial".
# Set to None to disable.
SCHEDULE_EXCLUDE_FILE_PATTERN = "Station Breaks/"

#######################################################################
# Miscellaneous configuration.

# Allow retrying file access if next video file cannot be opened.
# This can be useful if BASE_PATH is a network share.
# When RETRY_ATTEMPTS runs out, the script will abort if the next
# video file cannot be found. Set to 0 to not attempt to reopen
# missing files.
# Set RETRY_ATTEMPTS to -1 to retry infinitely.
# RETRY_PERIOD is the delay in seconds between each retry attempt.
RETRY_ATTEMPTS = 0
RETRY_PERIOD = 5

# Abort script if a file in the playlist cannot be found after retrying
# according to the settings above.
# Set to False to allow script to continue and skip the entry in the
# playlist. This allows the file to be included in future iterations
# of the playlist if it is found later.
EXIT_ON_FILE_NOT_FOUND = True

# Number of videos to keep in history log, saved in play_history.txt in
# BASE_PATH. Set to 0 to disable.
PLAY_HISTORY_LENGTH = 10

#######################################################################
# Configuration ends here.

SCRIPT_VERSION = "1.3.0"

def check_file(path):
    """Retry opening nonexistent files up to RETRY_ATTEMPTS.
    If file is found, returns True.
    If EXIT_ON_FILE_NOT_FOUND is True, throw exception if retry
    attempts don't succeed. If False, return False and continue.
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
                retry_attempts_string = f"{retry_attempts_remaining} attempts remaining."
            else:
                retry_attempts_string = "1 attempt remaining."
            retry_attempts_remaining -= 1

        elif retry_attempts_remaining == 0:
            if EXIT_ON_FILE_NOT_FOUND:
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),path)

            else:
                print(f"{path} not found. Continuing.")
                return False

        print(f"File not found: {path}.\nRetrying in {RETRY_PERIOD} seconds...\n{retry_attempts_string}")

        time.sleep(RETRY_PERIOD)

    else:
        return True


def get_extra_info(entry):
    """Split entry string at delimiter : and return a 2-element list.
    If the delimiter is not found, second element returned is an empty
    string.
    """
    entry = entry.split(" :",1)
    if len(entry) > 1:
        return entry
    else:
        return [entry[0],""]


def get_length(file):
    """Run ffprobe and retrieve length of file."""

    result = subprocess.run([FFPROBE_PATH,"-v","error","-select_streams","v:0",
                            "-show_entries","stream=duration","-of",
                            "default=noprint_wrappers=1:nokey=1",file],
                            capture_output=True,text=True).stdout

    if result == "":
        raise Exception("ffprobe was unable to read duration of: " + file)

    return result


def write_schedule(file_list,index,str_pattern,time_rewind = 0):
    """
    Write an HTML file containing file names and lengths read from a
    list containing video file paths. Optionally, include the most
    recently played file as well.
    """

    def get_next_file(list_sub,index_sub):
        """
        Get next file from list, looping the list around when it
        runs out.
        """
        list_iter = (i for i in list_sub[index_sub:])
        while True:
            try:
                yield next(list_iter)
            # Produce cycled list when generator runs out.
            except StopIteration:
                list_iter = itertools.cycle(list_sub)

    # Get previous file by iterating file_list in reverse
    # until a non-comment line that does not match
    # SCHEDULE_EXCLUDE_FILE_PATTERN is reached.
    prev_index = index - 1
    while True:
        # Remove extension from filenames and convert backslashes
        # to forward slashes.
        if file_list[prev_index] is not None:
            filename = get_extra_info(file_list[prev_index])

            filename[0] = os.path.splitext(filename[0])[0].replace("\\","/")
            if not filename[0].casefold().startswith(str_pattern):
                previous_file = {"name":filename[0],"extra_info":filename[1]}
                break

        prev_index -= 1

    # next_time contains start times of upcoming videos.
    # For the first file in file_list, this is the current system time.
    # Time is retrieved in UTC, to be converted to user's local time
    # when they load the schedule in their browser.
    next_time = datetime.datetime.utcnow()

    # Offset first program timing by elapsed_time read in the
    # second line of play_index.txt.
    duration = -time_rewind
    total_duration = -time_rewind

    coming_up_next = []

    # Calculate video file length and add to coming_up_next.
    for filename in get_next_file(file_list,index):
        if len(coming_up_next) > SCHEDULE_MAX_VIDEOS or total_duration > (SCHEDULE_UPCOMING_LENGTH * 60):
            break

        # Skip comment entries.
        if filename is None:
            continue

        # Extract extra info from playlist entry.
        filename = get_extra_info(filename)

        # Check file, and if entry cannot be found, skip the entry.
        result = check_file(os.path.join(BASE_PATH,filename[0]))
        if result is False:
            continue

        # Get length of next video in seconds from ffprobe, plus
        # ffmpeg padding.
        duration += int(float(get_length(os.path.join(BASE_PATH,filename[0])))) + VIDEO_PADDING
        total_duration += duration

        # Remove extension from filenames and convert backslashes
        # to forward slashes.
        filename[0] = os.path.splitext(filename[0])[0].replace("\\","/")

        # Append duration and stripped filename to list as tuple.
        # Skip files matching SCHEDULE_EXCLUDE_FILE_PATTERN, but keep
        # their durations.
        if not filename[0].casefold().startswith(str_pattern):
            coming_up_next.append({"name":filename[0],"time":next_time.strftime("%Y-%m-%d %H:%M:%S"),"extra_info":filename[1]})

        # Add length of current video to current time and use as
        # starting time for next video.
        next_time += datetime.timedelta(seconds=duration)
        duration = 0

    schedule_json_out = {"coming_up_next":coming_up_next,"previous_file":previous_file,"script_version":SCRIPT_VERSION}
    schedule_json_path = os.path.join(sys.path[0],"schedule.json")

    with open(schedule_json_path,"w+") as schedule_json:
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
        with open(MEDIA_PLAYLIST,"r") as media_playlist_file:
            media_playlist = media_playlist_file.read().splitlines()

    elif isinstance(MEDIA_PLAYLIST,list):
        media_playlist = MEDIA_PLAYLIST

    else:
        raise Exception("MEDIA_PLAYLIST is not a file or Python list.")

    # exclude_pattern is used in case-insensitive string comparison.
    if SCHEDULE_EXCLUDE_FILE_PATTERN is not None:
        if isinstance(SCHEDULE_EXCLUDE_FILE_PATTERN,str):
            exclude_pattern = (SCHEDULE_EXCLUDE_FILE_PATTERN.casefold().replace("\\","/"),)
        elif isinstance(SCHEDULE_EXCLUDE_FILE_PATTERN,list):
            exclude_pattern = tuple([i.casefold().replace("\\","/") for i in SCHEDULE_EXCLUDE_FILE_PATTERN])
    else:
        exclude_pattern = None

    # Change blank lines and comment entries in media_playlist to None.
    media_playlist = [i if i != "" and not i.startswith(";")
                      and not i.startswith("#")
                      and not i.startswith("//")
                      else None for i in media_playlist]

    while True:
        # Keep playlist index and elapsed time of current video and store
        # in file play_index.txt. Create it if it does not exist.
        play_index_contents = []

        try:
            with open(os.path.join(BASE_PATH,"play_index.txt"),"r") as index_file:
                play_index_contents = index_file.readlines()

        except FileNotFoundError:
            with open(os.path.join(BASE_PATH,"play_index.txt"),"w+") as index_file:
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

        # Play next video file, unless it is a comment entry.
        if media_playlist[play_index] is not None:

            video_time = datetime.datetime.now()
            video_file = get_extra_info(media_playlist[play_index])
            video_file_fullpath = os.path.join(BASE_PATH,video_file[0])

            # Check if video_file exists. If EXIT_ON_FILE_NOT_FOUND is
            # True and file is not found, skip the entry and continue.
            result = check_file(video_file_fullpath)

            if result:
                # If the second line of play_index.txt is greater than
                # REWIND_LENGTH, pass it to media player arguments.
                if elapsed_time < REWIND_LENGTH:
                    elapsed_time = 0
                else:
                    elapsed_time -= REWIND_LENGTH

                # Write history of played video files and timestamps,
                # limited to PLAY_HISTORY_LENGTH.
                if PLAY_HISTORY_LENGTH > 0:
                    try:
                        with open(os.path.join(BASE_PATH,"play_history.txt"),"r") as play_history:
                            play_history_buffer = play_history.readlines()

                    except FileNotFoundError:
                        with open(os.path.join(BASE_PATH,"play_history.txt"),"w+") as play_history:
                            play_history_buffer = []
                            play_history.close()

                    finally:
                        with open(os.path.join(BASE_PATH,"play_history.txt"),"w+") as play_history:
                            play_history_buffer.append(f"{video_time} - {video_file}\n")
                            play_history.writelines(play_history_buffer[-PLAY_HISTORY_LENGTH:])

                print("Now playing: " + video_file[0])

                schedule_p = Process(target=write_schedule,args=(media_playlist,play_index,exclude_pattern,elapsed_time))
                player_p = Process(target=subprocess.run,kwargs={"args":f"\"{MEDIA_PLAYER_PATH}\" {MEDIA_PLAYER_BEFORE_ARGUMENTS} \"{video_file_fullpath}\" {MEDIA_PLAYER_AFTER_ARGUMENTS}".format(elapsed_time),"shell":True})
                write_p = Process(target=write_index,args=(play_index,elapsed_time))

                player_p.start()
                if SCHEDULE_ENABLE:
                    schedule_p.start()
                write_p.start()
                player_p.join()
                if schedule_p.is_alive():
                    schedule_p.join()
                write_p.terminate()

        if play_index < len(media_playlist):
            play_index += 1

        else:
            # Reset index at end of playlist.
            play_index = 0

        with open(os.path.join(BASE_PATH,"play_index.txt"),"w") as index_file:
            index_file.write(str(play_index) + "\n0")


if __name__ == "__main__":
    main()
