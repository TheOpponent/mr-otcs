#!/usr/bin/env python3

#######################################################################
# Mr. OTCS
#
# https://github.com/TheOpponent/mr-otcs
# https://twitter.com/TheOpponent

import concurrent.futures
import datetime
import json
import os
import random
import shlex
import subprocess
import sys
import time
import traceback
from typing import Dict, Union

import psutil
import requests
from pebble import ProcessExpired, ProcessPool, concurrent

import config
import mail
import playlist
from config import print2
from streamstats import StreamStats
from utils import check_file, int_to_time, int_to_total_time


class BackgroundProcessError(Exception):
    """Raised when the background process closes prematurely for any
    reason. This exception is meant to be caught and used to restart
    the process.
    """


class ConnectionCheckError(Exception):
    """Raised when the connection check fails."""


class ExceptionCommand(BackgroundProcessError):
    """A manual %EXCEPTION command in the playlist."""


def rtmp_task(stats: StreamStats) -> subprocess.Popen:
    """Task for starting the RTMP broadcasting process."""

    command = shlex.split(f"{config.RTMP_STREAMER_PATH} {config.RTMP_ARGUMENTS}")

    # Check if RTMP ffmpeg is already running and terminate any processes
    # that match the command line.
    for proc in psutil.process_iter(["cmdline"]):
        if proc.info["cmdline"] == command:
            proc.kill()
            print2("notice", "Old RTMP process killed.")

    # Perform connection check regardless of previous check time, and only
    # continue once the check succeeds.
    if config.CHECK_URL is not None:
        print2("verbose2", "Checking connection before starting RTMP process.")
        while True:
            stats.force_connection_check()
            if check_connection_block(stats, exception=False):
                print2("verbose2", "Connection check succeeded.")
                break
            else:
                print2("error", "Connection check failed. Retrying in 5 seconds.")
                time.sleep(5)

    try:
        if config.RTMP_STREAMER_LOG is not None:
            with open(config.RTMP_STREAMER_LOG, "a", encoding="utf-8") as log:
                process = subprocess.Popen(command, stdout=log, stderr=log, text=True)
        else:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
    except subprocess.CalledProcessError as e:
        if config.RTMP_STREAMER_LOG is not None:
            print2(
                "error",
                f"RTMP process terminated, exit code {e.returncode}. Check {config.RTMP_STREAMER_LOG} for details.",
            )
        else:
            print2("error", f"RTMP process terminated, exit code {e.returncode}.")
        return e.returncode

    print2("info", "RTMP process started.")

    return process


def _check_connection(stats: StreamStats, skip=False, exception=True):
    if skip:
        return True

    random.shuffle(config.CHECK_URL)

    for link in config.CHECK_URL:
        try:
            requests.get(link, timeout=5)
            stats.set_connection_check_time()
            print2("verbose2", f"Connection to {link} succeeded.")
            return True
        except requests.exceptions.RequestException as e:
            if config.CHECK_STRICT:
                print2("error", f"Could not establish connection to {link}: {e}")
                if exception:
                    # If the check fails, force next check to ignore config.CHECK_INTERVAL setting.
                    stats.force_connection_check()
                    raise ConnectionCheckError(
                        f"Could not establish connection to {link}: {e}"
                    ) from e
                else:
                    return False
            else:
                print2("warn", f"Could not establish connection to {link}: {e}")
                continue

    return False


@concurrent.thread
def check_connection(stats: StreamStats, skip=False):
    """Check internet connection to links in `config.CHECK_URL`, tried
    in random order.

    If `skip` is True, the check always succeeds instantly.

    The connection check fails and raises `ConnectionCheckError` if the
    first link attempted times out when `config.CHECK_STRICT` is true,
    or if all links time out when it is false.

    Use `check_connection_block()` for a non-threaded check.
    """

    _check_connection(stats, skip)


def check_connection_block(stats: StreamStats, skip=False, exception=True):
    """Check internet connection to links in `config.CHECK_URL`, tried
    in random order. This version blocks until the check returns.

    Returns True if the request succeeds. If `skip` is True, this
    function always returns True.

    The connection check fails if the first link attempted times out
    when `config.CHECK_STRICT` is true, or if all links time out when
    it is false. If `exception` is True, raises `ConnectionCheckError`
    if the check fails. Otherwise, returns False.
    """

    return _check_connection(stats, skip, exception)


@concurrent.thread
def check_new_version(
    stats: StreamStats, skip=False
) -> Union[Dict[str, int], None, bool]:
    """Periodically check for a new version of Mr. OTCS.

    If no new version is available, returns None. If an error occurs
    when checking for a new version, returns False. If a new version
    is available, returns a dictionary containing the following keys:

    - \"new_version_name\": The release name.
    - \"new_version_prerelease\": True if the release is marked as a prerelease, False otherwise.
    - \"new_version_number\": The tag name.
    - \"new_version_notes\": The release notes, defined in the body.
    - \"new_version_url\": URL for the release page.
    """

    if skip:
        return None

    saved_major, saved_minor, saved_patch = stats.newest_version.split(".")
    url = "https://api.github.com/repos/theopponent/mr-otcs/releases"

    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            version_json = response.json()
            latest_version = None
            latest_prerelease = None

            for release in version_json:
                if release["prerelease"] == config.MAIL_ALERT_ON_NEW_PRERELEASE_VERSION:
                    # Tag names begin with "v". Strip the v for parsing.
                    latest_version = release["tag_name"][1:]
                    latest_major, latest_minor, latest_patch = latest_version.split(".")
                    latest_name = release["name"]
                    latest_prerelease = release["prerelease"]
                    latest_notes = release["body"]
                    latest_url = release["html_url"]
                    break
        else:
            print2(
                "warn",
                f"Failed to check latest version: {response.status_code} {response.reason}",
            )
            return False

        if (
            latest_major > saved_major
            or latest_minor > saved_minor
            or latest_patch > saved_patch
        ):
            if (
                latest_prerelease and config.MAIL_ALERT_ON_NEW_PRERELEASE_VERSION
            ) or not latest_prerelease:
                output = {
                    "new_version_name": latest_name,
                    "new_version_prerelease": latest_prerelease,
                    "new_version_number": latest_version,
                    "new_version_notes": latest_notes,
                    "new_version_url": latest_url,
                }
            else:
                output = None
        else:
            output = None
    except requests.exceptions.RequestException as e:
        print2("warn", f"Failed to check latest version: {type(e).__name__}: {str(e)}")
        return False

    # Always write version.json even if no new version is available, in the
    # event that a pre-release is available but the user does not request
    # updates for them.
    json_output = {"version": latest_version, "prerelease": latest_prerelease}

    try:
        with open("version.json", "w", encoding="utf-8") as version_file:
            json.dump(json_output, version_file)
    except OSError as e:
        print2("error", "Unable to write version.json: " + e)

    stats.newest_version = latest_version

    return output


def generate_status_report(stats: StreamStats):
    """Create a regular status report based on information in a
    `StreamStats` object, and add it to the e-mail daemon queue.
    """

    message = ""
    current_time = datetime.datetime.now(datetime.timezone.utc)
    program_runtime = int((current_time - stats.program_start_time).total_seconds())
    stream_runtime = int((current_time - stats.stream_start_time).total_seconds())

    message += (
        f"Report generated: {current_time.astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
        + f"Mr. OTCS version: {config.SCRIPT_VERSION}\n\n"
        + f"Program started: {stats.program_start_time.astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
        + f"Program runtime: {int_to_total_time(program_runtime)}\n"
        + f"Current stream started: {stats.stream_start_time.astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
        + f"Current stream duration: {int_to_time(stream_runtime)}\n"
        + f"Number of videos played since last stream restart: {stats.videos_since_restart}\n"
        + f"Total number of videos played: {stats.total_videos}\n\n"
        + f"Stream restarts: {stats.restarts}\n"
        + f"Stream errors: {stats.retries}\n"
        + f"Stream downtime: {int_to_total_time(stats.stream_downtime, round_down_zero=False)}\n"
        + f"Stream uptime rate: {round((program_runtime - stats.stream_downtime) / program_runtime * 100,2)}%"
    )

    if (exception_count := len(stats.exceptions)) > 0:
        message += (
            f"\n\n{exception_count} stream errors since last report:\n"
            if exception_count > 1
            else "\n\n1 stream error since last report:\n"
        )
        for exc, timestamp in stats.exceptions:
            message += f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {type(exc).__name__}: {str(exc)}\n"
        if config.MAIL_ALERT_MAX_ERRORS_REPORTED == 1:
            message += "(Only most recent error logged; earlier errors may have been truncated.)"
            if config.ERROR_LOG is not None:
                message += f" Check {config.ERROR_LOG}."
        elif exception_count == config.MAIL_ALERT_MAX_ERRORS_REPORTED:
            message += f"(Last {config.MAIL_ALERT_MAX_ERRORS_REPORTED} errors logged; earlier errors may have been truncated."
            if config.ERROR_LOG is not None:
                message += f" Check {config.ERROR_LOG}."
        stats.exceptions.clear()

    stats.mail_daemon.add_alert("status_report", message)


def encoder_task(
    file: str,
    rtmp_process: subprocess.Popen,
    stats: StreamStats,
    play_index=None,
    skip_time=0,
):
    """Task for encoding a video file from a playlist.

    Monitors the RTMP process id. If it is not running, or if the encoder
    process exits with a non-zero code, returns False. Otherwise, returns
    True.
    """

    command = shlex.split(
        f"{config.MEDIA_PLAYER_PATH} {config.MEDIA_PLAYER_ARGUMENTS.format(file=shlex.quote(file),skip_time=skip_time,video_padding=config.VIDEO_PADDING)}"
    )

    # Check if encoding ffmpeg is already running and terminate any processes
    # that match the command line.
    for proc in psutil.process_iter(["cmdline"]):
        if proc.info["cmdline"] == command:
            proc.kill()
            print2("notice", "Old encoder process killed.")

    write_index_wait = config.TIME_RECORD_INTERVAL

    # If the most recent connection check was too recent, ensure the
    # next check happens after the config.CHECK_INTERVAL delay.
    if config.CHECK_URL is not None:
        check_connection_wait = (
            datetime.datetime.now(datetime.timezone.utc) - stats.last_connection_check
        ).seconds
        if check_connection_wait < config.CHECK_INTERVAL:
            check_connection_wait = config.CHECK_INTERVAL - check_connection_wait
            check_connection_future = check_connection(stats, skip=True)
            print2(
                "verbose2",
                f"Skipping connection check as last check was done within the last {config.CHECK_INTERVAL} seconds. Performing next connection check in {check_connection_wait} seconds.",
            )
        else:
            check_connection_wait = config.CHECK_INTERVAL
            check_connection_future = check_connection(stats)
            print2("verbose2", "Checking connection.")

    try:
        if config.MEDIA_PLAYER_LOG is not None:
            with open(config.MEDIA_PLAYER_LOG, "a", encoding="utf-8") as log:
                process = subprocess.Popen(command, stdout=log, stderr=log, text=True)
        else:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
    except subprocess.CalledProcessError as e:
        print(e.stderr)
        print2(
            "error", f"Encoder process ended unexpectedly, exit code {e.returncode}."
        )
        return e.returncode

    # Poll both encoder and RTMP processes, and check internet connection once
    # per config.CHECK_INTERVAL. Return True if the encode finished
    # successfully and RTMP process is still running. If the connection check
    # fails, rewind config.CHECK_INTERVAL seconds.
    # Also write to play_index.txt in config.TIME_RECORD_INTERVAL seconds.
    while process.poll() is None and rtmp_process.poll() is None:
        if config.CHECK_URL is not None:
            check_connection_wait -= 1
            if check_connection_wait > 0:
                if (
                    check_connection_future.done()
                    and check_connection_future.exception() is not None
                ):
                    process.kill()
                    raise check_connection_future.exception()
            else:
                check_connection_wait = config.CHECK_INTERVAL
                check_connection_future = check_connection(stats)
                print2("verbose2", "Checking connection.")

        if play_index is not None:
            write_index_wait -= 1
            if write_index_wait <= 0:
                print2(
                    "verbose2",
                    f"Writing {play_index}, {stats.elapsed_time} to {config.PLAY_INDEX_FILE}.",
                )
                try:
                    write_index_future = playlist.write_index(play_index, stats)
                    write_index_future.result()
                except OSError as e:
                    print(e)
                    print2("error", f"Unable to write to {config.PLAY_INDEX_FILE}.")
                stats.elapsed_time += config.TIME_RECORD_INTERVAL
                write_index_wait = config.TIME_RECORD_INTERVAL

        # Check for new version during encoder task loop.
        if config.VERSION_CHECK_INTERVAL is not None:
            if datetime.datetime.now(datetime.timezone.utc) > stats.next_version_check:
                if (
                    stats.version_check_future is not None
                    and stats.version_check_future.done()
                ):
                    if (
                        new_version_info := stats.version_check_future.result()
                    ) is not None:
                        if isinstance(new_version_info, dict):
                            print2(
                                "notice",
                                f"New Mr. OTCS version available: {new_version_info['new_version_name']}",
                            )
                            print2(
                                "notice",
                                f"Download: {new_version_info['new_version_url']}",
                            )
                            if all(
                                (
                                    stats.mail_daemon_running(
                                        config.MAIL_ALERT_ON_NEW_VERSION
                                    ),
                                    (
                                        (
                                            new_version_info["new_version_prerelease"]
                                            and config.MAIL_ALERT_ON_NEW_PRERELEASE_VERSION
                                        )
                                        or not new_version_info[
                                            "new_version_prerelease"
                                        ]
                                    ),
                                ),
                            ):
                                stats.mail_daemon.add_alert(
                                    "new_version",
                                    message=new_version_info["new_version_notes"],
                                    version=new_version_info["new_version_name"],
                                    url=new_version_info["new_version_url"],
                                )
                        else:
                            print2("notice", "Retrying version check in 1 hour.")
                            stats.next_version_check = datetime.datetime.now(
                                datetime.timezone.utc
                            ) + datetime.timedelta(hours=1)
                    else:
                        print2("verbose", "No new version available.")
                    stats.version_check_future = None
                    stats.next_version_check = datetime.datetime.now(
                        datetime.timezone.utc
                    ) + datetime.timedelta(days=config.VERSION_CHECK_INTERVAL)
                elif stats.version_check_future is None:
                    stats.version_check_future = check_new_version(stats)
                    print2("verbose", "Checking for new version.")

        # Send status report during encoder task loop.
        if (
            stats.mail_daemon_running(config.MAIL_ALERT_STATUS_REPORT > 0)
            and datetime.datetime.now(datetime.timezone.utc) > stats.next_status_report
        ):
            print2("verbose", "Generating status report.")
            generate_status_report(stats)
            stats.next_status_report = datetime.datetime.now(
                datetime.timezone.utc
            ) + datetime.timedelta(days=config.MAIL_ALERT_STATUS_REPORT)

        time.sleep(1)

    if rtmp_process.poll() is not None:
        process.kill()
        raise BackgroundProcessError(
            f"RTMP process ended unexpectedly, exit code {rtmp_process.poll()}"
        )

    return process.poll()


def write_play_history(message):
    """Write history of played video files and timestamps, limited to
    `config.PLAY_HISTORY_LENGTH`.
    """

    if config.PLAY_HISTORY_FILE is None:
        return

    try:
        with open(config.PLAY_HISTORY_FILE, "r", encoding="utf-8") as play_history:
            play_history_buffer = play_history.readlines()
    except FileNotFoundError:
        play_history_buffer = []
    except OSError as e:
        print(e)
        print2(
            "error", f"Unable to read play history file at {config.PLAY_HISTORY_FILE}."
        )

    try:
        with open(config.PLAY_HISTORY_FILE, "w+", encoding="utf-8") as play_history:
            play_history_buffer.append(f"{datetime.datetime.now()} - {message}\n")
            play_history.writelines(play_history_buffer[-config.PLAY_HISTORY_LENGTH :])
    except OSError as e:
        print(e)
        print2(
            "error", f"Unable to write play history file to {config.PLAY_HISTORY_FILE}."
        )


def stop_stream(executor, restart=True):
    """Terminate old RTMP process(es), stop the executor, and make a
    new executor.
    """

    command = shlex.split(f"{config.RTMP_STREAMER_PATH} {config.RTMP_ARGUMENTS}")
    for proc in psutil.process_iter(["cmdline"]):
        if proc.info["cmdline"] != command:
            continue
        proc.kill()
        print2("notice", "RTMP process killed.")
    executor.stop()
    executor.join()
    if restart:
        executor = ProcessPool()
        return executor
    return None


def kill_media_player():
    """Attempt to terminate remaining processes with command line
    defined in `config.MEDIA_PLAYER_PATH`.
    """

    for proc in psutil.process_iter(["cmdline"]):
        if config.MEDIA_PLAYER_PATH in proc.info["cmdline"]:
            proc.kill()


def main():
    video_file: playlist.PlaylistEntry

    restarted: bool = False
    retried: bool = False
    instant_restarted: bool = False
    media_playlist = playlist.create_playlist()
    media_playlist_length = len(media_playlist)
    stats = StreamStats()
    total_elapsed_time = 0

    # Start RTMP broadcast task, to be stopped when total_elapsed_time
    # will exceed STREAM_TIME_BEFORE_RESTART.
    rtmp_process = rtmp_task(stats)
    stats.stream_start_time = datetime.datetime.now(datetime.timezone.utc)

    # Keep list of extra entries that get passed over, and pass it to
    # write_schedule().
    extra_entries = []

    executor = ProcessPool()

    if config.MAIL_ENABLE:
        stats.mail_daemon = mail.EMailDaemon()
        print2("info", f"Logging in to e-mail server {config.MAIL_SERVER}.")
        if stats.mail_daemon.test_login():
            print2("info", "Mail server login succeeded.")
        else:
            print2("error", "Mail server login failed.")
    else:
        stats.mail_daemon = None

    try:
        with open("version.json", "r", encoding="utf-8") as version_file:
            version_file_json = json.load(version_file)
            stats.newest_version = version_file_json["version"]
    except (FileNotFoundError, json.JSONDecodeError):
        stats.newest_version = config.SCRIPT_VERSION

    while True:
        try:
            # If config.STREAM_RESTART_BEFORE_VIDEO is defined, add its
            # length to total_elapsed_time ahead of time.
            if config.STREAM_RESTART_BEFORE_VIDEO is not None:
                if check_file(config.STREAM_RESTART_BEFORE_VIDEO):
                    next_video_length = playlist.get_length(
                        config.STREAM_RESTART_BEFORE_VIDEO
                    )
                    total_elapsed_time += next_video_length + config.VIDEO_PADDING
                else:
                    if stats.mail_daemon_running(config.MAIL_ALERT_ON_FILE_NOT_FOUND):
                        stats.mail_daemon.add_alert(
                            "file_not_found", message=config.STREAM_RESTART_BEFORE_VIDEO
                        )

            if restarted:
                print2("info", "Stream restarted.")
                write_play_history("Stream restarted.")
                if config.STREAM_RESTART_AFTER_VIDEO is not None:
                    if check_file(config.STREAM_RESTART_AFTER_VIDEO):
                        next_video_length = playlist.get_length(
                            config.STREAM_RESTART_AFTER_VIDEO
                        )
                        total_elapsed_time += next_video_length + config.VIDEO_PADDING
                        print2(
                            "play",
                            f"STREAM_RESTART_AFTER_VIDEO: {config.STREAM_RESTART_AFTER_VIDEO} - Length: {int_to_time(next_video_length)}.",
                        )
                        write_play_history(
                            f"STREAM_RESTART_AFTER_VIDEO: {config.STREAM_RESTART_AFTER_VIDEO}"
                        )
                        encoder = encoder_task(
                            config.STREAM_RESTART_AFTER_VIDEO, rtmp_process, stats
                        )
                        if encoder == 0:
                            total_elapsed_time += (
                                playlist.get_length(config.STREAM_RESTART_AFTER_VIDEO)
                                + config.VIDEO_PADDING
                            )

                    else:
                        if stats.mail_daemon_running(
                            config.MAIL_ALERT_ON_FILE_NOT_FOUND
                        ):
                            stats.mail_daemon.add_alert(
                                "file_not_found",
                                message=config.STREAM_RESTART_AFTER_VIDEO,
                            )

                restarted = False
                retried = False

            if instant_restarted:
                print2("info", "Stream restarted.")
                write_play_history("Stream restarted.")
                instant_restarted = False
                retried = False

            # Keep playlist index and elapsed time of current video and store
            # in file play_index.txt. Create it if it does not exist.
            play_index_contents = []

            try:
                with open(config.PLAY_INDEX_FILE, "r", encoding="utf-8") as index_file:
                    play_index_contents = index_file.readlines()
            except FileNotFoundError:
                print2(
                    "notice",
                    f"Play index reset due to {config.PLAY_INDEX_FILE} not found. Generating new file.",
                )
                with open(config.PLAY_INDEX_FILE, "w+", encoding="utf-8") as index_file:
                    index_file.write("0\n0")
                    play_index = 0
                    stats.elapsed_time = 0

            try:
                play_index = int(play_index_contents[0])
            except (IndexError, ValueError):
                play_index = 0

            try:
                stats.elapsed_time = int(play_index_contents[1])
            except (IndexError, ValueError):
                stats.elapsed_time = 0

            # Get next item in media_playlist that is a PlaylistEntry of type "normal".
            while True:
                # Reset index to 0 if it overruns the playlist and STOP_AFTER_LAST_VIDEO is not true.
                if play_index >= media_playlist_length:
                    if config.STOP_AFTER_LAST_VIDEO and stats.elapsed_time > 0:
                        print2("notice", "End of playlist reached. Stopping stream.")
                        play_index += 1
                        stop_stream(executor, restart=False)
                        total_time = int_to_total_time(
                            datetime.datetime.now(datetime.timezone.utc)
                            - stats.program_start_time
                        )
                        write_play_history(f"Stream ended after {total_time}.")
                        print2(
                            "verbose",
                            f"{stats.videos_since_restart} video(s) played since last restart.",
                        )
                        print2("notice", f"Mr. OTCS ran for {total_time}.")
                        try:
                            write_index_future = playlist.write_index(play_index, stats)
                            write_index_future.result()
                        except OSError as e:
                            print(e)
                            print2(
                                "error", f"Unable to write to {config.PLAY_INDEX_FILE}."
                            )
                            print2(
                                "error",
                                f"Update {config.PLAY_INDEX_FILE} manually: Line 1 with index {play_index}, line 2 with 0.",
                            )
                        if stats.mail_daemon_running(config.MAIL_ALERT_ON_PLAYLIST_END):
                            stats.mail_daemon.add_alert("playlist_end", urgent=True)
                        print2("notice", "Exiting.")
                        if os.name == "posix":
                            os.system("stty sane")
                        sys.exit(0)
                    else:
                        play_index = 0
                        stats.elapsed_time = 0
                        if stats.mail_daemon_running(
                            config.MAIL_ALERT_ON_PLAYLIST_LOOP
                        ):
                            stats.mail_daemon.add_alert("playlist_loop")

                if media_playlist[play_index][1].type == "normal":
                    break

                # If the program starts on a non-normal entry, ignore the elapsed time in play_index.txt.
                if stats.videos_since_restart == 0:
                    stats.elapsed_time = 0

                if media_playlist[play_index][1].type == "blank":
                    print2(
                        "verbose",
                        f"{media_playlist[play_index][0]}. Non-video file entry. Skipping.",
                    )
                    play_index += 1
                    continue

                if media_playlist[play_index][1].type == "extra":
                    print2(
                        "verbose",
                        f"{media_playlist[play_index][0]}. Extra: {media_playlist[play_index][1].info}",
                    )
                    extra_entries.append(media_playlist[play_index][1])
                    play_index += 1
                    continue

                # Execute directives for PlaylistEntry type "command".
                if media_playlist[play_index][1].type == "command":
                    if media_playlist[play_index][1].info == "RESTART":
                        if total_elapsed_time > config.STREAM_RESTART_MINIMUM_TIME:
                            restarted = True
                            stats.restarts += 1

                            print2(
                                "play",
                                f"{media_playlist[play_index][0]}. Executing RESTART command.",
                            )
                            write_play_history(
                                f"{media_playlist[play_index][0]}. %RESTART"
                            )

                            if config.STREAM_RESTART_BEFORE_VIDEO is not None:
                                print2(
                                    "play",
                                    f"STREAM_RESTART_BEFORE_VIDEO: {config.STREAM_RESTART_BEFORE_VIDEO} - Length: {int_to_time(playlist.get_length(config.STREAM_RESTART_BEFORE_VIDEO))}.",
                                )
                                write_play_history(
                                    f"STREAM_RESTART_BEFORE_VIDEO: {config.STREAM_RESTART_BEFORE_VIDEO}"
                                )
                                encoder = encoder_task(
                                    config.STREAM_RESTART_BEFORE_VIDEO,
                                    rtmp_process,
                                    stats,
                                )

                            stop_stream(executor)
                            stats.videos_since_restart = 0
                            total_elapsed_time = 0
                            print2(
                                "info",
                                f"Waiting {config.STREAM_RESTART_WAIT} seconds to restart.",
                            )
                            time.sleep(config.STREAM_RESTART_WAIT)
                            play_index += 1
                            rtmp_process = rtmp_task(stats)
                            stats.stream_start_time = datetime.datetime.now(
                                datetime.timezone.utc
                            )
                            break

                        print2(
                            "notice",
                            f"{media_playlist[play_index][0]}. RESTART command found, but not executing as less than {config.STREAM_RESTART_MINIMUM_TIME} minutes have passed.",
                        )
                        play_index += 1
                        continue

                    if media_playlist[play_index][1].info == "INSTANT_RESTART":
                        if total_elapsed_time > config.STREAM_RESTART_MINIMUM_TIME:
                            instant_restarted = True
                            stats.restarts += 1
                            print2(
                                "play",
                                f"{media_playlist[play_index][0]}. Executing INSTANT_RESTART command.",
                            )
                            write_play_history(
                                f"{media_playlist[play_index][0]}. %INSTANT_RESTART"
                            )
                            stop_stream(executor)
                            stats.videos_since_restart = 0
                            total_elapsed_time = 0
                            print2(
                                "info",
                                f"Waiting {config.STREAM_RESTART_WAIT} seconds to restart.",
                            )
                            time.sleep(config.STREAM_RESTART_WAIT)
                            play_index += 1
                            rtmp_process = rtmp_task(stats)
                            stats.stream_start_time = datetime.datetime.now(
                                datetime.timezone.utc
                            )
                            break
                        print2(
                            "notice",
                            f"{media_playlist[play_index][0]}. INSTANT_RESTART command found, but not executing as less than {config.STREAM_RESTART_MINIMUM_TIME} minutes have passed.",
                        )
                        play_index += 1
                        continue

                    if media_playlist[play_index][1].info == "STOP":
                        print2(
                            "notice",
                            f"{media_playlist[play_index][0]}. Executing STOP command.",
                        )
                        write_play_history(f"{media_playlist[play_index][0]}. %STOP")
                        play_index += 1
                        stop_stream(executor, restart=False)
                        total_time = int_to_total_time(
                            datetime.datetime.now(datetime.timezone.utc)
                            - stats.program_start_time
                        )
                        write_play_history(f"Stream ended after {total_time}.")
                        print2(
                            "verbose",
                            f"{stats.videos_since_restart} video(s) played since last restart.",
                        )
                        print2("notice", f"Mr. OTCS ran for {total_time}.")
                        try:
                            write_index_future = playlist.write_index(play_index, stats)
                            write_index_future.result()
                        except OSError as e:
                            print(e)
                            print2(
                                "error", f"Unable to write to {config.PLAY_INDEX_FILE}."
                            )
                            print2(
                                "error",
                                f"Update {config.PLAY_INDEX_FILE} manually: Line 1 with index {play_index}, line 2 with 0.",
                            )
                        if stats.mail_daemon_running(
                            config.MAIL_ALERT_ON_PLAYLIST_STOP
                        ):
                            stats.mail_daemon.add_alert(
                                "playlist_stop", urgent=True, line_num=play_index + 1
                            )
                        print2("notice", "Exiting.")
                        if os.name == "posix":
                            os.system("stty sane")
                        sys.exit(0)

                    if media_playlist[play_index][1].info.startswith("MAIL"):
                        if stats.mail_daemon_running(config.MAIL_ALERT_ON_COMMAND):
                            mail_command = media_playlist[play_index][1].info.split(
                                " ", 1
                            )
                            if len(mail_command) > 1 and not mail_command[1].isspace():
                                stats.mail_daemon.add_alert(
                                    "mail_command",
                                    message=mail_command[1],
                                    bypass_interval=True,
                                    line_num=play_index + 1,
                                )
                                print2(
                                    "notice",
                                    f"{play_index+1}. Sending manual e-mail alert: {mail_command[1]}",
                                )
                            else:
                                stats.mail_daemon.add_alert(
                                    "mail_command", bypass_interval=True
                                )
                                print2(
                                    "notice",
                                    f"{play_index+1}. Sending manual e-mail alert.",
                                )
                        else:
                            print2(
                                "verbose",
                                f"{play_index+1}. Not reading %MAIL command: E-mail alerts are disabled.",
                            )

                        play_index += 1
                        continue

                    if media_playlist[play_index][1].info.startswith("EXCEPTION"):
                        print2(
                            "notice",
                            f"{media_playlist[play_index][0]}. Executing EXCEPTION command.",
                        )
                        play_index += 1
                        playlist.write_index(play_index, stats)
                        raise ExceptionCommand(f"Line {play_index}")

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
                result = check_file(video_file.path)

                if result:
                    next_video_length = playlist.get_length(video_file.path)
                    if (
                        config.STREAM_TIME_BEFORE_RESTART == 0
                        or stats.videos_since_restart == 0
                    ) or (
                        stats.stream_time_remaining
                        - next_video_length
                        - config.VIDEO_PADDING
                        + stats.elapsed_time
                        > 0
                    ):
                        print2(
                            "play",
                            f"{media_playlist[play_index][0]}. {video_file.path} - Length: {int_to_time(next_video_length)}.",
                        )

                        # If the second line of play_index.txt is greater than
                        # REWIND_LENGTH, pass it to media player arguments.
                        # Do not rewind earlier than stats.video_resume_point.
                        if (
                            stats.elapsed_time < config.REWIND_LENGTH
                            or stats.elapsed_time >= next_video_length
                        ):
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
                            print2(
                                "notice",
                                f"Starting from {int_to_time(stats.elapsed_time)}.",
                            )

                        if (
                            stats.stream_time_remaining
                            - (next_video_length - stats.elapsed_time)
                            > 0
                        ):
                            print2(
                                "info",
                                f"{int_to_time(stats.stream_time_remaining - (next_video_length - stats.elapsed_time))} left before restart.",
                            )
                        else:
                            if config.STREAM_TIME_BEFORE_RESTART > 0:
                                print2(
                                    "notice",
                                    "STREAM_TIME_BEFORE_RESTART limit reached, but stream restart is deferred as no videos have completed yet.",
                                )

                        if config.PLAY_HISTORY_FILE is not None:
                            print2(
                                "verbose",
                                f"Writing play history file to {config.PLAY_HISTORY_FILE}.",
                            )
                            write_play_history(
                                f"{media_playlist[play_index][0]}. {video_file.path}"
                            )

                        # Always start video no earlier than stats.elapsed_time, which is read from
                        # play_index.txt file at the start of the loop.
                        # If stats.elapsed_time is less than config.REWIND_LENGTH, assume the
                        # encoder failed and restart from stats.video_restart_point.
                        while True:
                            if retried and config.STREAM_WAIT_AFTER_RETRY > 0:
                                print2(
                                    "notice",
                                    f"Waiting {config.STREAM_WAIT_AFTER_RETRY} seconds before retrying stream.",
                                )
                                time.sleep(config.STREAM_WAIT_AFTER_RETRY)

                            # Write schedule only once per video file.
                            if config.SCHEDULE_PATH is not None:
                                # Check if current video name matches config.SCHEDULE_EXCLUDE_FILE_PATTERN,
                                # and only generate a schedule file if it does not.
                                if (
                                    config.SCHEDULE_EXCLUDE_FILE_PATTERN is not None
                                    and not video_file.name.casefold().startswith(
                                        config.SCHEDULE_EXCLUDE_FILE_PATTERN
                                    )
                                ):
                                    if (
                                        stats.schedule_future is not None
                                        and not stats.schedule_future.done()
                                    ):
                                        print2(
                                            "warn",
                                            "Aborting schedule file upload for the previous video.",
                                        )
                                        if stats.schedule_future.cancel():
                                            print2(
                                                "notice",
                                                "Schedule future cancelled.",
                                            )
                                        else:
                                            print2(
                                                "warn",
                                                "Failed to cancel schedule future.",
                                            )
                                    else:
                                        stats.schedule_future = playlist.write_schedule(
                                            media_playlist,
                                            play_index,
                                            stats,
                                            extra_entries,
                                            retried,
                                        )

                                    # Clear extra_entries after writing schedule.
                                    extra_entries = []
                                else:
                                    print2(
                                        "notice",
                                        f"Not writing schedule for {video_file.name}: Name matches SCHEDULE_EXCLUDE_FILE_PATTERN.",
                                    )

                            # Send an e-mail alert if the stream resumed after an error.
                            if retried:
                                if stats.mail_daemon_running(
                                    config.MAIL_ALERT_ON_STREAM_RESUME
                                ):
                                    stats.mail_daemon.add_alert(
                                        "stream_resume",
                                        bypass_interval=True,
                                        exception=stats.mail_daemon.last_exception,
                                        exception_time=stats.mail_daemon.last_exception_time,
                                    )
                                    stats.update_stream_downtime()

                            print2("info", "Encoding started.")
                            encoder_result = encoder_task(
                                video_file.path,
                                rtmp_process,
                                stats,
                                play_index,
                                stats.elapsed_time,
                            )

                            # Calculate total time of encoding in seconds and update
                            # total_elapsed_time and stats.stream_time_remaining.
                            exit_time = (
                                datetime.datetime.now() - video_start_time
                            ).seconds
                            total_elapsed_time += exit_time
                            stats.stream_time_remaining -= exit_time

                            # Increment play_index if encode succeeded.
                            if encoder_result == 0:
                                retried = False
                                print2("info", "Video encoded successfully.")
                                stats.elapsed_time = 0
                                stats.video_resume_point = 0
                                stats.videos_since_restart += 1
                                stats.total_videos += 1
                                print2(
                                    "info",
                                    f"Elapsed stream time: {int_to_time(total_elapsed_time)}.",
                                )
                                if play_index > media_playlist_length:
                                    # Reset index at end of playlist.
                                    print2("verbose", "Resetting play index: 0")
                                    play_index = 0
                                else:
                                    play_index += 1
                                    print2(
                                        "verbose",
                                        f"Incrementing play index: {play_index}",
                                    )

                                with open(
                                    config.PLAY_INDEX_FILE, "w", encoding="utf-8"
                                ) as index_file:
                                    index_file.write(str(play_index) + "\n0")

                                break

                            # Retry if encoder process fails.
                            retried = True
                            stats.retries += 1
                            if stats.stream_time_remaining > (
                                next_video_length - exit_time
                            ):
                                if (
                                    stats.elapsed_time - config.REWIND_LENGTH
                                    > stats.video_resume_point
                                ):
                                    stats.rewind(config.REWIND_LENGTH)
                                    stats.video_resume_point = stats.elapsed_time
                                print2(
                                    "warn",
                                    f"Encoding failed. Retrying from {int_to_time(stats.elapsed_time)}.",
                                )
                                print2(
                                    "info",
                                    f"{int_to_time(stats.stream_time_remaining - (next_video_length - stats.elapsed_time))} left before restart.",
                                )
                            else:
                                # If the remaining length of the video is greater than
                                # stats.stream_time_remaining, force a restart by breaking
                                # this loop and causing the next iteration to go to restart.
                                print2(
                                    "warn",
                                    "Encoding failed. Insufficient time remaining to retry. Restarting stream.",
                                )
                                stats.stream_time_remaining = 0
                                stats.videos_since_restart += 1
                                break

                    else:
                        print2("notice", "STREAM_TIME_BEFORE_RESTART limit reached.")
                        restarted = True
                        stats.restarts += 1
                        if config.STREAM_RESTART_BEFORE_VIDEO is not None:
                            print2(
                                "play",
                                f"STREAM_RESTART_BEFORE_VIDEO: {config.STREAM_RESTART_BEFORE_VIDEO} - Length: {int_to_time(playlist.get_length(config.STREAM_RESTART_BEFORE_VIDEO))}.",
                            )
                            write_play_history(
                                f"STREAM_RESTART_BEFORE_VIDEO: {config.STREAM_RESTART_BEFORE_VIDEO}"
                            )
                            encoder = encoder_task(
                                config.STREAM_RESTART_BEFORE_VIDEO, rtmp_process, stats
                            )
                        print2(
                            "verbose",
                            f"{stats.videos_since_restart} video(s) played since last restart.",
                        )
                        executor = stop_stream(executor)
                        stats.videos_since_restart = 0
                        total_elapsed_time = 0
                        print2(
                            "notice",
                            f"Waiting {config.STREAM_RESTART_WAIT} seconds to restart stream.",
                        )
                        time.sleep(config.STREAM_RESTART_WAIT)
                        rtmp_process = rtmp_task(stats)
                        stats.stream_start_time = datetime.datetime.now(
                            datetime.timezone.utc
                        )
                        stats.stream_time_remaining = config.STREAM_TIME_BEFORE_RESTART
                        continue

                else:
                    if stats.mail_daemon_running(config.MAIL_ALERT_ON_FILE_NOT_FOUND):
                        stats.mail_daemon.add_alert(
                            "file_not_found",
                            message=video_file.path,
                            line_num=play_index + 1,
                        )
                    stats.elapsed_time = 0
                    stats.video_resume_point = 0
                    if play_index > media_playlist_length:
                        # Reset index at end of playlist.
                        print2("verbose", "Resetting play index: 0")
                        play_index = 0
                    else:
                        play_index += 1
                        print2("verbose", f"Incrementing play index: {play_index}")

                    with open(
                        config.PLAY_INDEX_FILE, "w", encoding="utf-8"
                    ) as index_file:
                        index_file.write(str(play_index) + "\n0")

                    continue

            else:
                print2(
                    "warn", f"{media_playlist[play_index][0]}. Unrecognized entry type."
                )
                play_index += 1

        except (ProcessExpired, BackgroundProcessError, ConnectionCheckError) as e:
            # If the RTMP process is terminated for any reason,
            # stop the encoder process immediately, rewind the video
            # if it advanced past one rewind interval since last encode,
            # and attempt to restart the stream.
            print2("error", f"{type(e).__name__}: {str(e)}")
            write_play_history(
                f"Stream stopped due to exception: {type(e).__name__}: {str(e)}"
            )
            stats.exceptions.append((e, datetime.datetime.now()))
            stats.last_exception_time = datetime.datetime.now(datetime.timezone.utc)

            # Do not send an e-mail on connection check failure.
            if stats.mail_daemon_running(config.MAIL_ALERT_ON_STREAM_DOWN):
                stats.mail_daemon.last_exception = e
                stats.mail_daemon.last_exception_time = datetime.datetime.now()
                if not isinstance(e, ConnectionCheckError):
                    stats.mail_daemon.add_alert(
                        "stream_down",
                        exception=e,
                        exception_time=stats.mail_daemon.last_exception_time,
                        bypass_interval=True,
                        urgent=True,
                    )
            print2("error", "Stream interrupted. Restarting.")
            print2(
                "verbose",
                f"{stats.videos_since_restart} video(s) played since last restart.",
            )
            retried = True
            stats.retries += 1
            if stats.elapsed_time - config.REWIND_LENGTH > stats.video_resume_point:
                stats.rewind(config.REWIND_LENGTH)
                stats.video_resume_point = stats.elapsed_time

            executor = stop_stream(executor)
            kill_media_player()
            stats.videos_since_restart = 0
            rtmp_process = rtmp_task(stats)
            stats.stream_start_time = datetime.datetime.now(datetime.timezone.utc)
            stats.stream_time_remaining = config.STREAM_TIME_BEFORE_RESTART
            continue

        except KeyboardInterrupt:
            try:
                if config.STREAM_MANUAL_RESTART_DELAY > 0:
                    print2(
                        "notice",
                        f"Restarting stream. Press Ctrl-C again within {config.STREAM_MANUAL_RESTART_DELAY} second(s) to exit.",
                    )
                    print2(
                        "verbose",
                        f"{stats.videos_since_restart} video(s) played since last restart.",
                    )
                    retried = True
                    stats.restarts += 1
                    if (
                        stats.elapsed_time - config.REWIND_LENGTH
                        > stats.video_resume_point
                    ):
                        stats.rewind(config.REWIND_LENGTH)
                        stats.video_resume_point = stats.elapsed_time

                    executor = stop_stream(executor)
                    kill_media_player()
                    time.sleep(config.STREAM_MANUAL_RESTART_DELAY)
                    stats.videos_since_restart = 0
                    rtmp_process = rtmp_task(stats)
                    stats.stream_start_time = datetime.datetime.now(
                        datetime.timezone.utc
                    )
                    stats.stream_time_remaining = config.STREAM_TIME_BEFORE_RESTART
                    continue
                else:
                    raise KeyboardInterrupt

            except KeyboardInterrupt:
                print2("notice", "Exiting Mr. OTCS. Stopping RTMP process.")
                stop_stream(executor, restart=False)
                total_time = int_to_total_time(
                    datetime.datetime.now(datetime.timezone.utc)
                    - stats.program_start_time
                )
                write_play_history(f"Stream ended after {total_time}.")
                print2(
                    "verbose",
                    f"{stats.videos_since_restart} video(s) played since last restart.",
                )
                print2("notice", f"Mr. OTCS ran for {total_time}.")
                print2("notice", "Exiting.")
                if os.name == "posix":
                    os.system("stty sane")
                sys.exit(130)

        except Exception as e:
            stop_stream(executor, restart=False)
            total_time = int_to_total_time(
                datetime.datetime.now(datetime.timezone.utc) - stats.program_start_time
            )
            if stats.mail_daemon_running(config.MAIL_ALERT_ON_PROGRAM_ERROR):
                stats.mail_daemon.add_alert(
                    "program_error",
                    exception=e,
                    exception_time=datetime.datetime.now(),
                    traceback=traceback.format_exc(),
                    urgent=True,
                    total_time=total_time,
                )
            stats.mail_daemon.stop()
            write_play_history(
                f"Stream stopped due to exception: {type(e).__name__}: {str(e)}"
            )
            write_play_history(f"Stream ended after {total_time}.")
            kill_media_player()
            print2(
                "fatal",
                f"Fatal error encountered: {type(e).__name__}: {str(e)}. Terminating stream.",
            )
            print2("notice", f"Mr. OTCS ran for {total_time}.")
            if os.name == "posix":
                os.system("stty sane")
            raise e


if __name__ == "__main__":
    print2("info", f"Mr. OTCS version {config.SCRIPT_VERSION}")
    print2("info", "https://github.com/TheOpponent/mr-otcs")
    print2("info", "========================================")
    main()
