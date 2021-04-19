import datetime
import errno
import itertools
import os
import subprocess
import sys
import time
from multiprocessing import Process

#######################################################################
# Configuration.

# Program paths. Use absolute paths.
# ffprobe is optional if HTML schedule will not be used.
MEDIA_PLAYER_PATH = "/usr/bin/ffmpeg"
FFPROBE_PATH = "/usr/bin/ffprobe"

# Number of seconds of black video to add between each video.
# This is added to schedule durations for each video.
# This can be ignored if not using ffmpeg.
FFMPEG_PADDING = 2

# Arguments to pass to media player. This should be whatever is
# necessary to immediately exit the player after playback is completed.
# MEDIA_PLAYER_BEFORE_ARGUMENTS are passed before the input file.
# MEDIA_PLAYER_AFTER_ARGUMENTS are passed after the input file.
MEDIA_PLAYER_BEFORE_ARGUMENTS = "-hide_banner -re -i"
MEDIA_PLAYER_AFTER_ARGUMENTS = f"-filter_complex \"tpad=stop_duration={FFMPEG_PADDING};apad=pad_dur={FFMPEG_PADDING}\" -vcodec libx264 -b:v 1100k -acodec aac -b:a 128k -f flv -framerate 30 -g 60 rtmp://{rtmp_address}"

# Base path for all video files, including trailing slash.
# This path will also contain play_index.txt and play_history.txt.
BASE_PATH = "/media/videos/"

# Video files, including subdirectories. This can be a Python list
# containing strings with filenames in BASE_PATH or a string with a
# path to a text file containing one filename in BASE_PATH per line.
# Items starting with comment characters ; # or // and blank lines will
# be skipped.
MEDIA_PLAYLIST = "/home/pi/list.txt"

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

# Allow retrying file access if next video file cannot be opened.
# This can be useful if BASE_PATH is a network share.
# If RETRY_ATTEMPTS is set to 0, the script will abort if the next
# video file cannot be found.
# Set RETRY_ATTEMPTS to -1 to retry infinitely.
# RETRY_PERIOD is the delay in seconds between each retry attempt.
RETRY_ATTEMPTS = 0
RETRY_PERIOD = 5

# Number of videos to keep in history log, saved in play_history.txt in
# BASE_PATH. Set to 0 to disable.
PLAY_HISTORY_LENGTH = 10

# Path for HTML schedule.
# See template.html for the file to be read by this script.
# Set to None to disable writing schedule.
SCHEDULE_PATH = "/var/www/schedule.html"

# Number of upcoming shows to write in schedule.
# Set SCHEDULE_UPCOMING_LENGTH to the total number of minutes of
# video to add to the schedule, and SCHEDULE_MAX_VIDEOS to limit
# the number of videos.
# Setting too high can cause MemoryError.
SCHEDULE_UPCOMING_LENGTH = 240
SCHEDULE_MAX_VIDEOS = 15


#######################################################################
# Function definitions.

def check_file(path):
    """Retry opening nonexistant files up to RETRY_ATTEMPTS."""

    retry_attempts_remaining = RETRY_ATTEMPTS

    # If RETRY_ATTEMPTS is -1, don't print number of attempts
    # remaining.
    if retry_attempts_remaining < 0:
        retry_attempts_string = ""

    while not os.path.isfile(path):
        # Print number of attempts remaining.
        if retry_attempts_remaining > 0:
            if retry_attempts_remaining > 1:
                retry_attempts_string = "{} attempts remaining.\n".format(retry_attempts_remaining)
            else:
                retry_attempts_string = "1 attempt remaining.\n"
            retry_attempts_remaining -= 1

        # If retry_attempts_remaining is 0 and file is not found,
        # raise exception.
        elif retry_attempts_remaining == 0:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),path)

        print("File not found: {}.\nRetrying in {} seconds...\n{}".format(path,RETRY_PERIOD,retry_attempts_string))

        time.sleep(RETRY_PERIOD)
        continue

    else:
        return


def write_schedule(file_list,index,str_pattern):
    """
    Write an HTML file containing file names and lengths read from a list
    containing video file paths. Optionally, include the most recently played
    file as well.
    """

    def get_length(file):
        """Run ffprobe and retrieve length of file."""

        result = subprocess.run([FFPROBE_PATH,"-v","error","-select_streams","v:0",
                                "-show_entries","stream=duration","-of",
                                "default=noprint_wrappers=1:nokey=1",file],
                                capture_output=True,text=True).stdout

        if result == "":
            raise Exception("ffprobe was unable to read duration of: " + file)

        return result

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

    # Get previous file by iterating file_list in reverse
    # until a non-comment line that does not match
    # SCHEDULE_EXCLUDE_FILE_PATTERN is reached.
    prev_index = index - 1
    while True:
        if file_list[prev_index] is not None:
            if not file_list[prev_index].casefold().startswith(str_pattern):
                previous_file = file_list[prev_index]
                break
        else:
            prev_index -= 1

    # next_time contains start times of upcoming videos.
    # For the first file in file_list, this is the current system time.
    # Time is retrieved in UTC, to be converted to user's local time
    # when they load the schedule in their browser.
    next_time = datetime.datetime.utcnow()

    if previous_file != "":
        previous_file = os.path.splitext(previous_file)[0].replace("\\","/")

    coming_up_next = []
    duration = 0
    total_duration = 0

    # Calculate video file length and add to coming_up_next.
    for filename in get_next_file(file_list,index):
        if len(coming_up_next) > SCHEDULE_MAX_VIDEOS or total_duration > (SCHEDULE_UPCOMING_LENGTH * 60):
            break

        # Skip comment entries.
        if filename is None:
            continue

        # TODO: Use check_file() for schedule generation.

        # Get length of next video in seconds from ffprobe, plus
        # ffmpeg padding.
        duration += int(float(get_length(os.path.join(BASE_PATH,filename)))) + FFMPEG_PADDING
        total_duration += duration

        # Remove extension from filenames and convert backslashes
        # to forward slashes.
        filename = os.path.splitext(filename)[0].replace("\\","/")

        # Append duration and stripped filename to list as tuple.
        # Skip files matching SCHEDULE_EXCLUDE_FILE_PATTERN, but keep
        # their durations.
        if not filename.casefold().startswith(str_pattern):
            coming_up_next.append((next_time,filename))

        # Add length of current video to current time and use as
        # starting time for next video.
        next_time += datetime.timedelta(seconds=duration)
        duration = 0


    # Format coming_up_next list into string suitable for assigning as
    # JavaScript array of objects.
    js_array = "[" + ",".join(["{{time:'{}',name:'{}'}}".format(i,n.replace("'",r"\'")) for i,n in coming_up_next]) + "]"

    # Generate HTML contents.
    with open(os.path.join(sys.path[0],"template.html"),"r") as html_template:
        html_contents = html_template.read()

    html_contents = html_contents.format(js_array=js_array,previous_file=previous_file)

    with open(SCHEDULE_PATH,"w") as html_file:
        html_file.write(html_contents)

    # Upload html_file to a publicly accessible location
    # using pysftp or something similar if necessary.

def loop(media_playlist,str_pattern):
    """Loop over playlist indefinitely."""

    def play():
        """Play a single entry in the playlist."""

        # Skip comment entries and exit loop immediately.
        if media_playlist[play_index] == None:
            return

        video_time = datetime.datetime.now()
        video_file = media_playlist[play_index]
        video_file_fullpath = os.path.join(BASE_PATH,video_file)

        # Check if video_file exists and raise exception if it does
        # not.
        check_file(video_file_fullpath)

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
                    play_history_buffer.append("{},{}\n".format(video_time,video_file))
                    play_history.writelines(play_history_buffer[-PLAY_HISTORY_LENGTH:])

        print("Now playing: " + video_file)

        # If HTML schedule writing is enabled, retrieve next videos in
        # list up to SCHEDULE_UPCOMING_LENGTH and write_schedule in
        # second process.
        if SCHEDULE_PATH != None:

            schedule_p = Process(target=write_schedule,args=(media_playlist,play_index,str_pattern))
            player_p = Process(target=subprocess.run,kwargs={"args":"\"{}\" {} \"{}\" {}".format(MEDIA_PLAYER_PATH,MEDIA_PLAYER_BEFORE_ARGUMENTS,video_file_fullpath,MEDIA_PLAYER_AFTER_ARGUMENTS),"shell":True})

            player_p.start()
            schedule_p.start()
            player_p.join()
            schedule_p.join()

        # If scheduling is disabled, simply play files in single
        # process.
        else:
            result = subprocess.run("\"{}\" {} \"{}\" {}".format(MEDIA_PLAYER_PATH,MEDIA_PLAYER_BEFORE_ARGUMENTS,video_file_fullpath,MEDIA_PLAYER_AFTER_ARGUMENTS),shell=True)

    # Keep playlist index and store in file play_index.txt. Create it
    # if it does not exist. Reset index to 0 if it overruns the list.
    try:
        with open(os.path.join(BASE_PATH,"play_index.txt"),"r") as index_file:
            play_index = int(index_file.read())
            media_playlist[play_index]

    except (FileNotFoundError, IndexError) as e:
        with open(os.path.join(BASE_PATH,"play_index.txt"),"w") as index_file:
            index_file.write("0")
            play_index = 0

    # Play file.
    play()

    if play_index < len(media_playlist):

        # Increment play_index and write play_index.txt in BASE_PATH.
        play_index = play_index + 1

    else:
        # Reset index at end of playlist.
        play_index = 0

    with open(os.path.join(BASE_PATH,"play_index.txt"),"w") as index_file:
        index_file.write(str(play_index))


#######################################################################
# Main loop.

if __name__ == "__main__":

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
    media_playlist = [i if i != "" and not i.startswith(";") and not i.startswith("#") and not i.startswith("//") else None for i in media_playlist]

    while True:
        loop(media_playlist,exclude_pattern)
