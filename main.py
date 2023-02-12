#!/usr/bin/env python3

#######################################################################
# Mr. OTCS
#
# https://github.com/TheOpponent/mr-otcs
# https://twitter.com/TheOpponent

import datetime
import shlex
import subprocess
import time
from concurrent.futures import TimeoutError

import psutil
from pebble import ProcessExpired, ProcessPool

import config
import playlist
from headers import *


class BackgroundProcessError(Exception):
    """Raised when the background process closes prematurely for any reason.
    This exception is meant to be caught and used to restart the process."""
    pass


def rtmp_task(process=None) -> subprocess.Popen:
    """Task for starting the RTMP broadcasting process."""

    command = shlex.split(f"{config.RTMP_STREAMER_PATH} {config.RTMP_ARGUMENTS}")

    # Check if RTMP ffmpeg is already running and terminate any processes
    # that match the command line.
    for proc in psutil.process_iter(['cmdline']):
        if proc.info['cmdline'] != command:
            continue
        else:
            proc.terminate()
            if config.VERBOSE:
                print(f"{info} Old RTMP process terminated.")

    try:
        process = subprocess.Popen(command)
    except subprocess.CalledProcessError as e:
        print(f"{error} RTMP process terminated at {datetime.datetime.now()}, exit code {e.returncode}.")
        return e.returncode

    if config.VERBOSE:
        print(f"{info} RTMP process started at {datetime.datetime.now()}.")

    return process


def encoder_task(file: str,rtmp_task: subprocess.Popen,skip_time=0):
    """Task for encoding a video file from a playlist.
    Monitors the RTMP process id. If it is not running, or if the encoder
    process exits with a non-zero code, returns False. Otherwise, returns
    True.

    This task also handles uploading the schedule file via SFTP."""

    command = shlex.split(f"{config.MEDIA_PLAYER_PATH} {config.MEDIA_PLAYER_ARGUMENTS.format(file=file,skip_time=skip_time)}")

    # Check if encoding ffmpeg is already running and terminate any processes
    # that match the command line.
    for proc in psutil.process_iter(['cmdline']):
        if proc.info['cmdline'] != command:
            continue
        else:
            proc.terminate()
            if config.VERBOSE:
                print(f"{info} Old encoder process terminated.")

    try:
        process = subprocess.Popen(command)
    except subprocess.CalledProcessError as e:
        print(f"{error} Encoder process terminated at {datetime.datetime.now()}, exit code {e.returncode}.")
        return e.returncode

    # Upload schedule file to SFTP server after starting encoding.
    if config.SCHEDULE_PATH is not None and config.REMOTE_ADDRESS is not None:
        if config.VERBOSE:
            print(f"{info} Uploading {config.SCHEDULE_PATH} to SFTP server {config.REMOTE_ADDRESS}.")
        sftp_future = playlist.upload_sftp()

        try:
            err = sftp_future.exception(timeout=10)
            if err is None:
                if config.VERBOSE:
                    print(f"{info} SFTP upload successful.")
            else:
                raise err
        except TimeoutError:
            print(f"{warn} SFTP upload timed out.")
        except Exception as e:
            print(e)
            print(f"{warn} SFTP upload failed.")

    # Poll both encoder and RTMP processes.
    # Return True if the encode finished successfully and RTMP process is still running.
    while process.poll() is None and rtmp_task.poll() is None:
        time.sleep(1)

    if rtmp_task.poll() is not None:
        process.terminate()
        raise BackgroundProcessError(f"{error} RTMP process terminated unexpectedly at {datetime.datetime.now()}, exit code {rtmp_task.poll()}. Restarting stream.")
    else:
        return process.poll()


def write_play_history(video_file, play_index, video_time):
    """Write history of played video files and timestamps,
    limited to PLAY_HISTORY_LENGTH."""

    try:
        with open(config.PLAY_HISTORY_FILE,"r") as play_history:
            play_history_buffer = play_history.readlines()
    except FileNotFoundError:
        with open(config.PLAY_HISTORY_FILE,"w+") as play_history:
            play_history_buffer = []
            play_history.close()
    finally:
        with open(config.PLAY_HISTORY_FILE,"w+") as play_history:
            play_history_buffer.append(f"{video_time} - {play_index}. {video_file}\n")
            play_history.writelines(play_history_buffer[-config.PLAY_HISTORY_LENGTH:])


def restart_stream(executor,rtmp_process):
    rtmp_process.terminate()
    executor.stop()
    executor.join()


def int_to_time(seconds):
    """Returns a time string containing hours, minutes, and seconds
    from an amount of seconds."""

    hr, min = divmod(seconds,3600)
    min, sec = divmod(min,60)

    return f"{hr:02d}:{min:02d}:{sec:02d}"


def main():

    video_file: playlist.PlaylistEntry

    print(f"{info} Mr. OTCS version {config.SCRIPT_VERSION}")
    print(f"{info} https://github.com/TheOpponent/mr-otcs")

    if config.STREAM_URL == "":
        print(f"{error} STREAM_URL in {config.config_file} is blank. Enter a valid stream location and run main.py again.")
        exit(1)

    restarted = False
    media_playlist = playlist.create_playlist()
    total_elapsed_time = 0

    # Start RTMP broadcast task, to be stopped when total_elapsed_time
    # will exceed STREAM_TIME_BEFORE_RESTART.
    rtmp_process = rtmp_task()

    # Keep list of extra entries that get passed over, and pass it to
    # write_schedule().
    extra_entries = []

    stats = playlist.StreamStats()

    while True:
        try:
            executor = ProcessPool()

            # Set initial exit_time. exit_time is set to elapsed time since
            # playback began and compared to start time stored in video_time in
            # next loop.
            exit_time = datetime.datetime.now()

            # If config.STREAM_RESTART_BEFORE_VIDEO is defined, add its
            # length to total_elapsed_time before it plays.
            if config.STREAM_RESTART_BEFORE_VIDEO is not None:
                total_elapsed_time += playlist.get_length(config.STREAM_RESTART_BEFORE_VIDEO)
                print(f"{info} {config.STREAM_RESTART_BEFORE_VIDEO} to play before stream restarts: {total_elapsed_time} seconds.\n{info} {config.STREAM_TIME_BEFORE_RESTART - total_elapsed_time} seconds left before restart.")

            # Keep playlist index and elapsed time of current video and store
            # in file play_index.txt. Create it if it does not exist.
            play_index_contents = []

            if restarted:
                print(f"{info} Stream restarted at {datetime.datetime.now()}.")
                if config.STREAM_RESTART_AFTER_VIDEO is not None:
                    encoder = encoder_task(config.STREAM_RESTART_AFTER_VIDEO,rtmp_process)
                    if encoder == 0:
                        total_elapsed_time += playlist.get_length(config.STREAM_RESTART_AFTER_VIDEO) + config.VIDEO_PADDING

                restarted = False

            try:
                with open(config.PLAY_INDEX_FILE,"r") as index_file:
                    play_index_contents = index_file.readlines()

            except FileNotFoundError:
                with open(config.PLAY_INDEX_FILE,"w+") as index_file:
                    index_file.write("0\n0")
                    play_index = 0
                    stats.elapsed_time = 0

            # Reset index to 0 if it overruns the playlist.
            try:
                play_index = int(play_index_contents[0])
                media_playlist[play_index]
            except IndexError:
                play_index = 0

            try:
                stats.elapsed_time = int(play_index_contents[1])
            except IndexError:
                stats.elapsed_time = 0

            # Get next item in media_playlist that is a PlaylistEntry of type "normal".
            while True:
                if play_index >= len(media_playlist):
                    play_index = 0

                if media_playlist[play_index][1].type == "normal":
                    break

                if media_playlist[play_index][1].type == "blank":
                    if config.VERBOSE:
                        print(f"{info} {media_playlist[play_index][0]}. Non-video file entry. Skipping.")
                    play_index += 1
                    continue

                elif media_playlist[play_index][1].type == "extra":
                    if config.VERBOSE:
                        print(f"{info} {media_playlist[play_index][0]}. Extra: {media_playlist[play_index][1].info}")
                    extra_entries.append(media_playlist[play_index][1])
                    play_index += 1
                    continue

                # Execute directives for PlaylistEntry type "command".
                elif media_playlist[play_index][1].type == "command":
                    if media_playlist[play_index][1].info == "RESTART":
                        if total_elapsed_time > config.STREAM_RESTART_MINIMUM_TIME:
                            restarted = True

                            print(f"{play} {media_playlist[play_index][0]}. Executing RESTART command.")

                            if config.STREAM_RESTART_BEFORE_VIDEO is not None:
                                encoder_task(config.STREAM_RESTART_BEFORE_VIDEO,rtmp_process)

                            restart_stream(executor,rtmp_process)
                            total_elapsed_time = 0

                            if config.VERBOSE:
                                print(f"{info} Waiting {config.STREAM_RESTART_WAIT} seconds to restart.")
                            time.sleep(config.STREAM_RESTART_WAIT)
                            play_index += 1
                            rtmp_process = rtmp_task()
                            break

                        else:
                            print(f"{info} {media_playlist[play_index][0]}. RESTART command found, but not executing as less than {config.STREAM_RESTART_MINIMUM_TIME} seconds have passed.")

                        play_index += 1
                        continue

                else:
                    break

            # If stream was just restarted due to %RESTART directive, restart loop.
            if restarted:
                continue

            # Play video file entry.
            if play_index >= len(media_playlist):
                play_index = 0
            if media_playlist[play_index][1].type == "normal":
                video_file = media_playlist[play_index][1]
                video_time = datetime.datetime.now()
                result = playlist.check_file(video_file.path)

                if result:
                    next_video_length = playlist.get_length(video_file.path) - stats.elapsed_time
                    if config.STREAM_TIME_BEFORE_RESTART == 0 or total_elapsed_time + next_video_length < config.STREAM_TIME_BEFORE_RESTART:
                        if config.VERBOSE:
                            print(f"{play} {media_playlist[play_index][0]}. {video_file.path} - Length: {int_to_time(next_video_length)}.")
                            if config.STREAM_TIME_BEFORE_RESTART > 0:
                                print(f"{info} {int_to_time(config.STREAM_TIME_BEFORE_RESTART - total_elapsed_time - next_video_length)} left before restart.")
                        else:
                            print(f"{play} {media_playlist[play_index][0]}. {video_file.path}")

                        if stats.elapsed_time > 0:
                            print(f"{info} Starting from {int_to_time(stats.elapsed_time)}.")

                        # If the second line of play_index.txt is greater than
                        # REWIND_LENGTH, pass it to media player arguments.
                        if stats.elapsed_time < config.REWIND_LENGTH:
                            stats.elapsed_time = 0
                        else:
                            # If video took less than REWIND_LENGTH to play
                            # (e.g. repeatedly failing to start or first loop
                            # of script), do not rewind.
                            if (exit_time - video_time).seconds > config.REWIND_LENGTH:
                                stats.elapsed_time -= config.REWIND_LENGTH

                        if config.PLAY_HISTORY_FILE is not None:
                            write_play_history(video_file.name,media_playlist[play_index][0],video_time)

                        # Write schedule only once per video file.
                        if config.SCHEDULE_PATH is not None:
                            if config.VERBOSE:
                                print(f"{info} Writing schedule file to {config.SCHEDULE_PATH}.")
                            playlist.write_schedule(media_playlist,play_index,stats,stats.elapsed_time,config.STREAM_TIME_BEFORE_RESTART - total_elapsed_time,extra_entries)

                        # Always start video no earlier than stats.elapsed_time, which is read from
                        # play_index.txt file at the start of the loop.
                        # playlist.elapsed_time is incremented in playlist.write_index as a global.
                        # If playlist.elapsed_time is less than config.REWIND_LENGTH, assume the
                        # encoder failed and restart from stats.elapsed_time again.
                        while True:
                            if config.VERBOSE:
                                print(f"{info} Encoding started on {video_time}.")
                            if stats.elapsed_time < config.REWIND_LENGTH:
                                stats.elapsed_time = 0
                            write_index_future = executor.schedule(playlist.write_index,[play_index,stats.elapsed_time,stats])
                            encoder_result = encoder_task(video_file.path,rtmp_process,stats.elapsed_time)

                            if encoder_result == 0:
                                if config.VERBOSE:
                                    print(f"{info} Video encoded successfully.")
                                # Increment play_index and add video length to
                                # total_elapsed_time upon successful playback.
                                write_index_future.cancel()
                                exit_time = datetime.datetime.now()
                                total_elapsed_time += next_video_length
                                extra_entries = []
                                if config.VERBOSE:
                                    print(f"{info} Elapsed stream time: {total_elapsed_time} seconds.")
                                if play_index < len(media_playlist):
                                    play_index += 1
                                    print(f"{info} Incrementing play index: {play_index}")
                                else:
                                    # Reset index at end of playlist.
                                    play_index = 0

                                with open(config.PLAY_INDEX_FILE,"w") as index_file:
                                    index_file.write(str(play_index) + "\n0")

                                break

                            # Retry if encoder process fails.
                            else:
                                if stats.elapsed_time < config.REWIND_LENGTH:
                                    stats.elapsed_time = 0
                                restart_time = stats.elapsed_time

                                print(f"{info} Encoding failed. Retrying from {int_to_time(restart_time)}.")
                                # time.sleep(1)

                    else:
                        print(f"{info} STREAM_TIME_BEFORE_RESTART limit reached.")
                        restarted = True
                        if config.STREAM_RESTART_BEFORE_VIDEO is not None:
                            print(f"{play} STREAM_RESTART_BEFORE_VIDEO: {config.STREAM_RESTART_BEFORE_VIDEO}")
                            encoder = encoder_task(config.STREAM_RESTART_BEFORE_VIDEO,rtmp_process)

                        restart_stream(executor,rtmp_process)
                        extra_entries = []
                        print(f"{info} Waiting {config.STREAM_RESTART_WAIT} seconds to restart stream.")
                        total_elapsed_time = 0
                        time.sleep(config.STREAM_RESTART_WAIT)
                        rtmp_process = rtmp_task()
                        continue

            else:
                print(f"{warn} {media_playlist[play_index][0]}. Unrecognized entry type.")
                play_index += 1

        except (ProcessExpired, BackgroundProcessError) as e:
            # If the RTMP process is terminated for any reason,
            # stop the encoder process immediately and rewind.
            print(e)
            restart_stream(executor,rtmp_process)
            rtmp_process = rtmp_task()
            continue

        except KeyboardInterrupt:
            print(f"{info} Stopping RTMP process.")
            rtmp_process.terminate()
            executor.stop()
            executor.join()
            print(f"{info} Exiting.")
            exit(0)

        except Exception as e:
            print(e)
            rtmp_process.terminate()
            executor.stop()
            executor.join()
            print(f"{error} Fatal error encountered on {datetime.datetime.now()}. Terminating stream.")
            raise e


if __name__ == "__main__":
    main()