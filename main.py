#!/usr/bin/env python3

#######################################################################
# Mr. OTCS
#
# https://github.com/TheOpponent/mr-otcs
# https://twitter.com/TheOpponent

import datetime
import os
import random
import shlex
import subprocess
import time
from concurrent.futures import TimeoutError

import psutil
import requests
from pebble import ProcessExpired, ProcessPool, concurrent

import config
import playlist
from config import print2


class BackgroundProcessError(Exception):
    """Raised when the background process closes prematurely for any reason.
    This exception is meant to be caught and used to restart the process."""
    pass


def rtmp_task() -> subprocess.Popen:
    """Task for starting the RTMP broadcasting process."""

    command = shlex.split(f"{config.RTMP_STREAMER_PATH} {config.RTMP_ARGUMENTS}")

    # Check if RTMP ffmpeg is already running and terminate any processes
    # that match the command line.
    for proc in psutil.process_iter(['cmdline']):
        if proc.info['cmdline'] != command:
            continue
        else:
            proc.kill()
            print2("notice","Old RTMP process found and killed.")

    try:
        process = subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print2("error",f"RTMP process terminated on {datetime.datetime.now()}, exit code {e.returncode}.")
        return e.returncode

    print2("info",f"RTMP process started on {datetime.datetime.now()}.")

    return process


@concurrent.thread
def check_connection(stats: playlist.StreamStats, skip=False, exception=True):
    """Check internet connection to links in config.CHECK_URL, tried in random
    order. Returns True if one request succeeds. If all links fail to respond,
    raise BackgroundProcessError. If exception is False, return False instead.
    """

    if skip:
        return True

    random.shuffle(config.CHECK_URL)

    for link in config.CHECK_URL:
        try:
            requests.get(link,timeout=5)
            stats.last_connection_check = datetime.datetime.now(datetime.timezone.utc)
            print2("verbose2",f"Connection to {link} succeeded on {datetime.datetime.now()}.")
            return True
        except requests.exceptions.RequestException as e:
            print(e)
            print2("warn",f"Could not establish connection to {link}.")
            continue

    if exception:
        # If the check fails, force next check to ignore config.CHECK_INTERVAL setting.
        stats.last_connection_check = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=config.CHECK_INTERVAL)
        raise BackgroundProcessError("Could not establish connection to any links in CHECK_URL.")
    else:
        return False


def encoder_task(file: str,rtmp_task: subprocess.Popen,stats: playlist.StreamStats,play_index=None,skip_time=0):
    """Task for encoding a video file from a playlist.
    Monitors the RTMP process id. If it is not running, or if the encoder
    process exits with a non-zero code, returns False. Otherwise, returns
    True.

    This task also handles uploading the schedule file via SSH."""

    command = shlex.split(f"{config.MEDIA_PLAYER_PATH} {config.MEDIA_PLAYER_ARGUMENTS.format(file=file,skip_time=skip_time)}")

    # Check if encoding ffmpeg is already running and terminate any processes
    # that match the command line.
    for proc in psutil.process_iter(['cmdline']):
        if proc.info['cmdline'] != command:
            continue
        else:
            proc.kill()
            print2("notice","Old encoder process killed.")

    write_index_wait = config.TIME_RECORD_INTERVAL

    # If the most recent connection check was too recent, ensure the
    # next check happens after the config.CHECK_INTERVAL delay.
    check_connection_wait = (datetime.datetime.now(datetime.timezone.utc) - stats.last_connection_check).seconds
    if check_connection_wait < config.CHECK_INTERVAL:
        check_connection_wait = config.CHECK_INTERVAL - check_connection_wait
        check_connection_future = check_connection(stats,skip=True)
        print2("verbose2",f"Skipping connection check as last check was done within the last {config.CHECK_INTERVAL} seconds. Performing next connection check in {check_connection_wait} seconds.")
    else:
        check_connection_wait = config.CHECK_INTERVAL
        check_connection_future = check_connection(stats)
        print2("verbose2",f"Checking connection on {datetime.datetime.now(datetime.timezone.utc)}.")

    try:
        process = subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(e.stderr)
        print2("error",f"Encoder process ended unexpectedly on {datetime.datetime.now()}, exit code {e.returncode}.")
        return e.returncode

    # Upload schedule file to SSH server after starting encoding.
    if config.SCHEDULE_PATH is not None and config.REMOTE_ADDRESS is not None:
        print2("verbose",f"Uploading {config.SCHEDULE_PATH} to SSH server {config.REMOTE_ADDRESS}.")
        ssh_future = playlist.upload_ssh()

        try:
            err = ssh_future.exception(timeout=10)
            if err is None:
                print2("verbose","SSH upload successful.")
            else:
                raise err
        except TimeoutError:
            print2("warn","SSH upload timed out.")
        except Exception as e:
            print(e)
            print2("warn","SSH upload failed.")

    # Poll both encoder and RTMP processes, and check internet connection once
    # per minute. Return True if the encode finished successfully and RTMP
    # process is still running. If the connection check fails, rewind
    # config.CHECK_INTERVAL seconds.
    # Also write to play_index.txt in config.TIME_RECORD_INTERVAL seconds.
    while process.poll() is None and rtmp_task.poll() is None:
        check_connection_wait -= 1
        if check_connection_wait > 0:
            if check_connection_future.done():
                if check_connection_future.exception() is not None:
                    process.kill()
                    raise check_connection_future.exception()
        else:
            check_connection_wait = config.CHECK_INTERVAL
            check_connection_future = check_connection(stats)
            print2("verbose2",f"Checking connection on {datetime.datetime.now()}.")

        if play_index is not None:
            write_index_wait -= 1
            if write_index_wait <= 0:
                print2("verbose2",f"Writing {play_index}, {stats.elapsed_time} to {config.PLAY_INDEX_FILE}.")
                try:
                    write_index_future = playlist.write_index(play_index,stats)
                    write_index_future.result()
                except OSError as e:
                    print(e)
                    print2("error",f"Unable to write to {config.PLAY_INDEX_FILE}.")
                stats.elapsed_time += config.TIME_RECORD_INTERVAL
                write_index_wait = config.TIME_RECORD_INTERVAL
        time.sleep(1)

    if rtmp_task.poll() is not None:
        process.kill()
        raise BackgroundProcessError(f"RTMP process ended unexpectedly on {datetime.datetime.now()}, exit code {rtmp_task.poll()}. Restarting stream.")
    else:
        return process.poll()


def write_play_history(message):
    """Write history of played video files and timestamps,
    limited to PLAY_HISTORY_LENGTH."""

    try:
        with open(config.PLAY_HISTORY_FILE,"r") as play_history:
            play_history_buffer = play_history.readlines()
    except FileNotFoundError:
        with open(config.PLAY_HISTORY_FILE,"w+") as play_history:
            play_history_buffer = []
    finally:
        try:
            with open(config.PLAY_HISTORY_FILE,"w+") as play_history:
                play_history_buffer.append(f"{datetime.datetime.now()} - {message}\n")
                play_history.writelines(play_history_buffer[-config.PLAY_HISTORY_LENGTH:])
        except OSError as e:
            print(e)
            print2("error",f"Unable to write play history file to {config.PLAY_HISTORY_FILE}.")


def stop_stream(executor,restart=True):
    """Terminate old RTMP process(es), stop the executor, and make a new executor."""

    command = shlex.split(f"{config.RTMP_STREAMER_PATH} {config.RTMP_ARGUMENTS}")
    for proc in psutil.process_iter(['cmdline']):
        if proc.info['cmdline'] != command:
            continue
        else:
            proc.kill()
            print2("notice","RTMP process killed.")
    executor.stop()
    executor.join()
    if restart:
        executor = ProcessPool()
        return executor


def int_to_time(seconds):
    """Returns a time string containing hours, minutes, and seconds
    from an amount of seconds."""

    hr, min = divmod(seconds,3600)
    min, sec = divmod(min,60)

    return f"{hr}:{min:02d}:{sec:02d}"


def int_to_total_time(seconds):
    """Returns a plain time string containing days, hours, minutes, and
    seconds from an amount of seconds."""

    if seconds < 1:
        return "less than a second"

    days, hr = divmod(int(seconds),86400)
    hr, min = divmod(hr,3600)
    min, sec = divmod(min,60)
    string = []

    if days > 0:
        string.append(f"{days} days" if days != 1 else f"{days} day")
    if hr > 0:
        string.append(f"{hr} hours" if hr != 1 else f"{hr} hour")
    if min > 0:
        string.append(f"{min} minutes" if min != 1 else f"{min} minute")
    if sec > 0:
        string.append(f"{sec} seconds" if sec != 1 else f"{sec} second")

    return ', '.join(string)


def main():

    video_file: playlist.PlaylistEntry

    if config.STREAM_URL == "":
        print2("error",f"STREAM_URL in {config.config_file} is blank. Enter a valid stream location and run main.py again.")
        exit(1)

    restarted = False
    retried = False
    instant_restarted = False
    media_playlist = playlist.create_playlist()
    media_playlist_length = len(media_playlist)
    stats = playlist.StreamStats()
    total_elapsed_time = 0

    print2("verbose",f"Checking connection on {datetime.datetime.now(datetime.timezone.utc)}.")
    init_connection_check = check_connection(stats,exception=False)
    while True:
        try:
            if init_connection_check.result():
                break
        except TimeoutError as e:
            print2("error","Initial connection check failed. Retrying in 5 seconds.")
            time.sleep(5)
            init_connection_check = check_connection(stats,exception=False)
        else:
            break

    # Start RTMP broadcast task, to be stopped when total_elapsed_time
    # will exceed STREAM_TIME_BEFORE_RESTART.
    rtmp_process = rtmp_task()
    stats.stream_start_time = datetime.datetime.now(datetime.timezone.utc)

    # Keep list of extra entries that get passed over, and pass it to
    # write_schedule().
    extra_entries = []

    executor = ProcessPool()

    while True:
        try:

            # If config.STREAM_RESTART_BEFORE_VIDEO is defined, add its
            # length to total_elapsed_time ahead of time.
            if config.STREAM_RESTART_BEFORE_VIDEO is not None:
                if playlist.check_file(config.STREAM_RESTART_BEFORE_VIDEO):
                    next_video_length = playlist.get_length(config.STREAM_RESTART_BEFORE_VIDEO)
                    total_elapsed_time += next_video_length + config.VIDEO_PADDING

            if restarted:
                print2("info",f"Stream restarted on {datetime.datetime.now()}.")
                write_play_history(f"Stream restarted.")
                if config.STREAM_RESTART_AFTER_VIDEO is not None:
                    if playlist.check_file(config.STREAM_RESTART_AFTER_VIDEO):
                        next_video_length = playlist.get_length(config.STREAM_RESTART_AFTER_VIDEO)
                        total_elapsed_time += next_video_length + config.VIDEO_PADDING
                        print2("play",f"STREAM_RESTART_AFTER_VIDEO: {config.STREAM_RESTART_AFTER_VIDEO} - Length: {int_to_time(next_video_length)}.")
                        write_play_history(f"STREAM_RESTART_AFTER_VIDEO: {config.STREAM_RESTART_AFTER_VIDEO}")
                        encoder = encoder_task(config.STREAM_RESTART_AFTER_VIDEO,rtmp_process,stats)
                        if encoder == 0:
                            total_elapsed_time += playlist.get_length(config.STREAM_RESTART_AFTER_VIDEO) + config.VIDEO_PADDING

                restarted = False
                retried = False

            if instant_restarted:
                print2("info",f"Stream restarted on {datetime.datetime.now()}.")
                write_play_history(f"Stream restarted.")
                instant_restarted = False
                retried = False

            # Keep playlist index and elapsed time of current video and store
            # in file play_index.txt. Create it if it does not exist.
            play_index_contents = []

            try:
                with open(config.PLAY_INDEX_FILE,"r") as index_file:
                    play_index_contents = index_file.readlines()
            except FileNotFoundError:
                print2("notice",f"Play index reset due to {config.PLAY_INDEX_FILE} not found. Generating new file.")
                with open(config.PLAY_INDEX_FILE,"w+") as index_file:
                    index_file.write("0\n0")
                    play_index = 0
                    stats.elapsed_time = 0

            try:
                play_index = int(play_index_contents[0])
            except IndexError:
                play_index = 0

            try:
                stats.elapsed_time = int(play_index_contents[1])
            except IndexError:
                stats.elapsed_time = 0

            # Get next item in media_playlist that is a PlaylistEntry of type "normal".
            while True:

                # Reset index to 0 if it overruns the playlist.
                if play_index >= media_playlist_length:
                    play_index = 0

                if media_playlist[play_index][1].type == "normal":
                    break

                if media_playlist[play_index][1].type == "blank":
                    print2("verbose",f"{media_playlist[play_index][0]}. Non-video file entry. Skipping.")
                    play_index += 1
                    continue

                elif media_playlist[play_index][1].type == "extra":
                    print2("verbose",f"{media_playlist[play_index][0]}. Extra: {media_playlist[play_index][1].info}")
                    extra_entries.append(media_playlist[play_index][1])
                    play_index += 1
                    continue

                # Execute directives for PlaylistEntry type "command".
                elif media_playlist[play_index][1].type == "command":
                    if media_playlist[play_index][1].info == "RESTART":
                        if total_elapsed_time > config.STREAM_RESTART_MINIMUM_TIME:
                            restarted = True

                            print2("play",f"{media_playlist[play_index][0]}. Executing RESTART command.")
                            write_play_history(f"{media_playlist[play_index][0]}. %RESTART")

                            if config.STREAM_RESTART_BEFORE_VIDEO is not None:
                                print2("play",f"STREAM_RESTART_BEFORE_VIDEO: {config.STREAM_RESTART_BEFORE_VIDEO} - Length: {int_to_time(playlist.get_length(config.STREAM_RESTART_BEFORE_VIDEO))}.")
                                write_play_history(f"STREAM_RESTART_BEFORE_VIDEO: {config.STREAM_RESTART_BEFORE_VIDEO}")
                                encoder = encoder_task(config.STREAM_RESTART_BEFORE_VIDEO,rtmp_process,stats)

                            stop_stream(executor)
                            stats.videos_since_restart = 0
                            total_elapsed_time = 0
                            print2("info",f"Waiting {config.STREAM_RESTART_WAIT} seconds to restart.")
                            time.sleep(config.STREAM_RESTART_WAIT)
                            play_index += 1
                            rtmp_process = rtmp_task()
                            stats.stream_start_time = datetime.datetime.now(datetime.timezone.utc)
                            break

                        else:
                            print2("notice",f"{media_playlist[play_index][0]}. RESTART command found, but not executing as less than {config.STREAM_RESTART_MINIMUM_TIME} minutes have passed.")
                            play_index += 1
                            continue

                    elif media_playlist[play_index][1].info == "INSTANT_RESTART":
                        if total_elapsed_time > config.STREAM_RESTART_MINIMUM_TIME:
                            instant_restarted = True
                            print2("play",f"{media_playlist[play_index][0]}. Executing INSTANT_RESTART command.")
                            write_play_history(f"{media_playlist[play_index][0]}. %INSTANT_RESTART")
                            stop_stream(executor)
                            stats.videos_since_restart = 0
                            total_elapsed_time = 0
                            print2("info",f"Waiting {config.STREAM_RESTART_WAIT} seconds to restart.")
                            time.sleep(config.STREAM_RESTART_WAIT)
                            play_index += 1
                            rtmp_process = rtmp_task()
                            stats.stream_start_time = datetime.datetime.now(datetime.timezone.utc)
                            break
                        else:
                            print2("notice",f"{media_playlist[play_index][0]}. INSTANT_RESTART command found, but not executing as less than {config.STREAM_RESTART_MINIMUM_TIME} minutes have passed.")
                            play_index += 1
                            continue

                else:
                    break

            # If stream was just restarted due to %RESTART or %INSTANT_RESTART directive, restart loop.
            if restarted or instant_restarted:
                continue

            # Play video file entry. Ensure at least one video will always play each loop
            # regardless of stream time limits.
            if play_index >= media_playlist_length:
                play_index = 0
            if media_playlist[play_index][1].type == "normal":
                video_file = media_playlist[play_index][1]
                video_start_time = datetime.datetime.now()
                result = playlist.check_file(video_file.path)

                if result:
                    next_video_length = playlist.get_length(video_file.path)
                    if (config.STREAM_TIME_BEFORE_RESTART == 0 or stats.videos_since_restart == 0) or (stats.stream_time_remaining - next_video_length - config.VIDEO_PADDING + stats.elapsed_time > 0):
                        print2("play",f"{media_playlist[play_index][0]}. {video_file.path} - Length: {int_to_time(next_video_length)}.")

                        # If the second line of play_index.txt is greater than
                        # REWIND_LENGTH, pass it to media player arguments.
                        # Do not rewind earlier than stats.video_resume_point.
                        if stats.elapsed_time < config.REWIND_LENGTH or stats.elapsed_time >= next_video_length:
                            stats.elapsed_time = 0
                        else:
                            # If video took less than REWIND_LENGTH to play
                            # (e.g. repeatedly failing to start or first loop
                            # of script), do not rewind.
                            if stats.elapsed_time > stats.video_resume_point:
                                stats.rewind(config.REWIND_LENGTH)
                            else:
                                stats.elapsed_time = stats.video_resume_point

                        next_video_length += config.VIDEO_PADDING

                        if stats.elapsed_time > 0:
                            print2("notice",f"Starting from {int_to_time(stats.elapsed_time)}.")

                        if stats.stream_time_remaining - (next_video_length - stats.elapsed_time) > 0:
                            print2("info",f"{int_to_time(stats.stream_time_remaining - (next_video_length - stats.elapsed_time))} left before restart.")
                        else:
                            print2("notice","STREAM_TIME_BEFORE_RESTART limit reached, but stream restart is deferred as no videos have completed yet.")
                        if config.PLAY_HISTORY_FILE is not None:
                            print2("verbose",f"Writing play history file to {config.PLAY_HISTORY_FILE}.")
                            write_play_history(f"{media_playlist[play_index][0]}. {video_file.path}")

                        # Write schedule only once per video file.
                        if config.SCHEDULE_PATH is not None:
                            print2("verbose",f"Writing schedule file to {config.SCHEDULE_PATH}.")

                            # Check if current video name matches config.SCHEDULE_EXCLUDE_FILE_PATTERN,
                            # and only generate a schedule file if it does not.
                            if config.SCHEDULE_EXCLUDE_FILE_PATTERN is not None and not video_file.name.casefold().startswith(config.SCHEDULE_EXCLUDE_FILE_PATTERN):
                                schedule_future = playlist.write_schedule(media_playlist,play_index,stats,extra_entries)
                                # Clear extra_entries after writing schedule.
                                extra_entries = []
                            else:
                                print2("notice",f"Not writing schedule for {video_file.name}: Name matches SCHEDULE_EXCLUDE_FILE_PATTERN.")

                        # Always start video no earlier than stats.elapsed_time, which is read from
                        # play_index.txt file at the start of the loop.
                        # If stats.elapsed_time is less than config.REWIND_LENGTH, assume the
                        # encoder failed and restart from stats.video_restart_point.
                        while True:
                            print2("info",f"Encoding started on {video_start_time}.")
                            encoder_result = encoder_task(video_file.path,rtmp_process,stats,play_index,stats.elapsed_time)

                            # Calculate total time of encoding in seconds and update
                            # total_elapsed_time and stats.stream_time_remaining.
                            exit_time = (datetime.datetime.now() - video_start_time).seconds
                            total_elapsed_time += exit_time
                            stats.stream_time_remaining -= exit_time

                            # Increment play_index if encode succeeded.
                            if encoder_result == 0:
                                retried = False
                                print2("info","Video encoded successfully.")
                                stats.elapsed_time = 0
                                stats.video_resume_point = 0
                                stats.videos_since_restart += 1
                                print2("info",f"Elapsed stream time: {int_to_time(total_elapsed_time)}.")
                                if play_index > media_playlist_length:
                                    # Reset index at end of playlist.
                                    print2("verbose","Resetting play index: 0")
                                    play_index = 0
                                else:
                                    play_index += 1
                                    print2("verbose",f"Incrementing play index: {play_index}")

                                with open(config.PLAY_INDEX_FILE,"w") as index_file:
                                    index_file.write(str(play_index) + "\n0")

                                break

                            # Retry if encoder process fails.
                            else:
                                retried = True
                                if stats.stream_time_remaining > (next_video_length - exit_time):
                                    if stats.elapsed_time - config.REWIND_LENGTH > stats.video_resume_point:
                                        stats.rewind(config.REWIND_LENGTH)
                                        stats.video_resume_point = stats.elapsed_time
                                    print2("warn",f"Encoding failed. Retrying from {int_to_time(stats.elapsed_time)}.")
                                    print2("info",f"{int_to_time(stats.stream_time_remaining - (next_video_length - stats.elapsed_time))} left before restart.")
                                else:
                                    # If the remaining length of the video is greater than
                                    # stats.stream_time_remaining, force a restart by breaking
                                    # this loop and causing the next iteration to go to restart.
                                    print2("warn","Encoding failed. Insufficient time remaining to retry. Restarting stream.")
                                    stats.stream_time_remaining = 0
                                    stats.videos_since_restart += 1
                                    break

                    else:
                        print2("notice","STREAM_TIME_BEFORE_RESTART limit reached.")
                        restarted = True
                        if config.STREAM_RESTART_BEFORE_VIDEO is not None:
                            print2("play",f"STREAM_RESTART_BEFORE_VIDEO: {config.STREAM_RESTART_BEFORE_VIDEO} - Length: {int_to_time(playlist.get_length(config.STREAM_RESTART_BEFORE_VIDEO))}.")
                            write_play_history(f"STREAM_RESTART_BEFORE_VIDEO: {config.STREAM_RESTART_BEFORE_VIDEO}")
                            encoder = encoder_task(config.STREAM_RESTART_BEFORE_VIDEO,rtmp_process,stats)
                        print2("verbose",f"{stats.videos_since_restart} videos played since last restart.")
                        executor = stop_stream(executor)
                        stats.videos_since_restart = 0
                        total_elapsed_time = 0
                        print2("notice",f"Waiting {config.STREAM_RESTART_WAIT} seconds to restart stream.")
                        time.sleep(config.STREAM_RESTART_WAIT)
                        rtmp_process = rtmp_task()
                        stats.stream_start_time = datetime.datetime.now(datetime.timezone.utc)
                        stats.stream_time_remaining = config.STREAM_TIME_BEFORE_RESTART
                        continue

            else:
                print2("warn",f"{media_playlist[play_index][0]}. Unrecognized entry type.")
                play_index += 1

        except (ProcessExpired, BackgroundProcessError) as e:
            # If the RTMP process is terminated for any reason,
            # stop the encoder process immediately, rewind the video
            # if it advanced past one rewind interval since last encode,
            # and attempt to restart the stream.
            print2("error",e)
            write_play_history(f"Stream stopped due to exception: {e}")
            print2("error","Stream interrupted. Attempting to restart.")
            print2("verbose",f"{stats.videos_since_restart} videos played since last restart.")
            if stats.elapsed_time - config.REWIND_LENGTH > stats.video_resume_point:
                stats.rewind(config.REWIND_LENGTH)
                stats.video_resume_point = stats.elapsed_time
            executor = stop_stream(executor)
            time.sleep(1)
            stats.videos_since_restart = 0
            rtmp_process = rtmp_task()
            stats.stream_start_time = datetime.datetime.now(datetime.timezone.utc)
            stats.stream_time_remaining = config.STREAM_TIME_BEFORE_RESTART
            continue

        except KeyboardInterrupt:
            print2("notice","Stopping RTMP process.")
            stop_stream(executor,restart=False)
            total_time = int_to_total_time((datetime.datetime.now(datetime.timezone.utc) - stats.program_start_time).total_seconds())
            write_play_history(f"Stream ended after {total_time}.")
            print2("verbose",f"{stats.videos_since_restart} videos played since last restart.")
            print2("notice",f"Mr. OTCS ran for {total_time}.")
            print2("notice","Exiting.")
            if os.name == "posix":
                os.system("stty sane")
            exit(130)

        except Exception as e:
            print(e)
            stop_stream(executor,restart=False)
            total_time = int_to_total_time((datetime.datetime.now(datetime.timezone.utc) - stats.program_start_time).total_seconds())
            write_play_history(f"Stream stopped due to exception: {e}")
            write_play_history(f"Stream ended after {total_time}.")
            # Attempt to terminate remaining ffmpeg processes.
            for proc in psutil.process_iter(['cmdline']):
                if config.MEDIA_PLAYER_PATH not in proc.info['cmdline']:
                    continue
                else:
                    proc.kill()
            print2("fatal",f"Fatal error encountered on {datetime.datetime.now()}. Terminating stream.")
            print2("notice",f"Mr. OTCS ran for {total_time}.")
            if os.name == "posix":
                os.system("stty sane")
            raise e


if __name__ == "__main__":
    print2("info",f"Mr. OTCS version {config.SCRIPT_VERSION}")
    print2("info","https://github.com/TheOpponent/mr-otcs")
    print2("info","========================================")
    main()