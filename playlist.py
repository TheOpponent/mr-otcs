"""Functions for handling the playlist and schedule files."""

import datetime
import errno
import itertools
import json
import os
import threading
import time
from collections import deque
from typing import Generator, Tuple

import fabric
from pebble import concurrent
from pymediainfo import MediaInfo

import config
from config import print2
from streamstats import StreamStats


class PlaylistEntry:
    """Definition for playlist entries, parsed from a list or text file
    containing formatted playlist entry strings.

    A `PlaylistEntry` can be one of these types:
    - "normal": Contains a path to a video file.
    - "extra": A comment to be printed in the schedule page.
    - "command": A directive to control the stream.
    - "blank": A blank line in the playlist file, to keep line numbers aligned.

    The commands currently include:
    - `%RESTART`: Force the stream to restart. The video files defined in
    - `config.STREAM_RESTART_BEFORE_VIDEO` and `config.STREAM_RESTART_AFTER_VIDEO`,
    if any, will play before and after the restart.
    - `%INSTANT_RESTART`: Similar to `%RESTART`, but the above optional videos will
    not play.
    - `%MAIL`: Add a mail alert with the included message.
    - `%STOP`: End the stream immediately. The `play_index` will be incremented
    before exiting.

    When a `PlaylistEntry` is created, it stores only information based on the
    provided string. Video files may change before they are played, so
    duration and other information is calculated only as it is played.

    `self.name` will contain a relative path to a file name, or a blank string
    if `self.type` is not "normal".
    """

    type: str
    """One of 'normal', 'extra', 'command', or 'blank'. Normal entries contain
    information on a video file.
    """

    name: str
    """For normal entries, the name of this video as displayed in the schedule.
    This can be overwritten with an alternate name.
    """

    path: str
    "The full path to this video file."

    info: str
    """For normal and extra entries, any metadata attached to this entry.
    For command entries, the directive to run.
    """

    def __init__(self, entry):
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
            split_name = entry.split(" :", 1)
            self.name = os.path.splitext(split_name[0])[0]
            self.path = (
                os.path.join(config.BASE_PATH, "".join(split_name[0]))
                if not os.path.isabs(split_name[0])
                else split_name[0]
            )
            if len(split_name) > 1:
                self.info = split_name[1]
            else:
                self.info = ""


class PlaylistTestEntry(PlaylistEntry):
    """A `PlaylistEntry` intended for use in unit tests. It has an extra
    attribute, `length`, that will always be returned by `get_length()`.
    """

    def __init__(self, entry, length=60):
        super().__init__(entry)
        if self.type == "normal":
            self.path = None
            self.length = length


def get_length(video) -> int:
    """Retrieve length of a video file using pymediainfo."""

    if isinstance(video, PlaylistTestEntry):
        return video.length

    elif isinstance(video, PlaylistEntry):
        video = video.path

    elif video is None:
        return 0

    if isinstance(video, str):
        mediainfo = MediaInfo.parse(video)
        return int(float(mediainfo.video_tracks[0].duration) // 1000)

    raise ValueError("Expected PlaylistEntry, path, or None.")


def check_file(path, line_num=None, no_exit=False):
    """Retry opening nonexistent files up to `config.RETRY_ATTEMPTS`.

    If file is found, returns True.
    If `EXIT_ON_FILE_NOT_FOUND` is True, throw exception if retry
    attempts don't succeed. If False, return False and continue.
    no_exit overrides `EXIT_ON_FILE_NOT_FOUND`.
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
                retry_attempts_string = (
                    f"{retry_attempts_remaining} attempts remaining."
                )
            else:
                retry_attempts_string = "1 attempt remaining."
            retry_attempts_remaining -= 1

        elif retry_attempts_remaining == 0:
            if config.EXIT_ON_FILE_NOT_FOUND and not no_exit:
                if line_num is not None:
                    print2("fatal", f"Line {line_num}: {path} not found.")
                else:
                    print2("error", f"{path} not found.")
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)
            else:
                if line_num is not None:
                    print2("error", f"Line {line_num}: {path} not found. Continuing.")
                else:
                    print2("error", f"{path} not found. Continuing.")
                return False

        print2("error", f"File not found: {path}.")
        print2(
            "error",
            f"{retry_attempts_string} Retrying in {config.RETRY_PERIOD} seconds...",
        )

        time.sleep(config.RETRY_PERIOD)

    else:
        return True


def create_playlist() -> list[Tuple[int, PlaylistEntry]]:
    """Read `config.MEDIA_PLAYLIST`, which is set to either the path to a text
    file or a list, containing a sequence of playlist entries.

    Returns an enumerated list starting from 1 containing `PlaylistEntry`
    objects.
    """

    playlist = []

    # If config.MEDIA_PLAYLIST is a file, open the file.
    if isinstance(config.MEDIA_PLAYLIST, str):
        try:
            with open(
                config.MEDIA_PLAYLIST, "r", encoding="utf-8-sig"
            ) as media_playlist_file:
                media_playlist = media_playlist_file.read().splitlines()
        except FileNotFoundError:
            print2("fatal", f"Playlist file {config.MEDIA_PLAYLIST} not found.")
            exit(1)

    elif isinstance(config.MEDIA_PLAYLIST, list):
        media_playlist = config.MEDIA_PLAYLIST

    else:
        print2("error", "MEDIA_PLAYLIST is not a file or Python list.")
        exit(1)

    # Change blank lines and comment entries in media_playlist to None.
    media_playlist = [
        i if i != "" and not i.startswith((";", "#", "//")) else None
        for i in media_playlist
    ]

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
        if new_entry.type == "normal" and new_entry.name in config.ALT_NAMES:
            if isinstance(config.ALT_NAMES[new_entry.name], str):
                new_entry.name = config.ALT_NAMES[new_entry.name]
            else:
                print2(
                    "warn",
                    f"Alternate name for {new_entry.name} in alt_names.json is not a valid string.",
                )

        if config.VERBOSE & 0b1111111:
            if new_entry.type == "normal":
                if new_entry.info == "":
                    print2("verbose", f"Adding normal entry: {index}. {new_entry.name}")
                else:
                    print2(
                        "verbose",
                        f"Adding normal entry: {index}. {new_entry.name} - Extra info: {new_entry.info}",
                    )
            elif new_entry.type == "extra":
                print2("verbose", f"Adding extra entry: {index}. {new_entry.info}")
            elif new_entry.type == "command":
                print2("verbose", f"Adding command: {index}. {new_entry.info}")
            elif new_entry.type == "blank":
                print2("verbose", f"Blank line or comment: {index}.")
        playlist.append((index, new_entry))

        index += 1

    if config.STOP_AFTER_LAST_VIDEO:
        playlist.append((index, PlaylistEntry("%STOP")))

    if entry_count == 0:
        print2("fatal", f"No valid entries found in {config.MEDIA_PLAYLIST}.")
        exit(1)

    return playlist


def get_stream_restart_duration():
    """Helper function to add combined duration of
    config.STREAM_RESTART_BEFORE_VIDEO,
    config.STREAM_RESTART_AFTER_VIDEO,
    and config.STREAM_RESTART_WAIT.
    """

    duration = 0

    if config.STREAM_RESTART_BEFORE_VIDEO is not None and check_file(
        config.STREAM_RESTART_BEFORE_VIDEO, line_num=-1, no_exit=True
    ):
        duration += (
            get_length(config.STREAM_RESTART_BEFORE_VIDEO) + config.VIDEO_PADDING
        )
    if config.STREAM_RESTART_AFTER_VIDEO is not None and check_file(
        config.STREAM_RESTART_AFTER_VIDEO, line_num=-2, no_exit=True
    ):
        duration += get_length(config.STREAM_RESTART_AFTER_VIDEO) + config.VIDEO_PADDING
    duration += config.STREAM_RESTART_WAIT

    return duration


@concurrent.thread
def write_schedule(
    playlist: list,
    entry_index: int,
    stats: StreamStats,
    extra_entries=[],
    ignore_previous_files=False,
):
    """Write a JSON file containing file names and lengths read from playlist.
    The playlist, a list created by `create_playlist()`, is read starting from
    the entry_index.

    File names matching `config.SCHEDULE_EXCLUDE_FILE_PATTERN` are not included
    in the output, but their durations are calculated and added to the next
    eligible entry.

    `first_length_offset` is the starting time of the currently playing video,
    if it did not start from the beginning.

    `stream_time_remaining` is used to predict time-based automatic stream
    restarts. The calculated length of the first video in the sliced
    playlist is subtracted from this amount.

    Any `PlaylistEntry` objects in the `extra_entries` list will be added
    before the first video in the generated JSON. Only "extra" type entries
    are currently supported; all others are ignored.

    The JSON file includes the following keys:
    - `program_start_time`: The time this program began, in UTC.
    - `start_time`: The time this function was called, which approximates
    to the time the currently playing video file began, in UTC.
    - `coming_up_next`: Nested JSON objects with a combined duration not
    exceeding `config.SCHEDULE_MAX_VIDEOS` or `config.SCHEDULE_UPCOMING_LENGTH`.
    previous_files: Nested JSON objects popped from a deque containing the
    `coming_up_next` objects.
    - `script_version`: The current script version.

    The `coming_up_next` objects have the following keys:
    - `type`: Either "normal" or "extra".
    - `name`: The video name for normal entries, a blank string for extra entries.
    - `time`: Approximate time this video started, in UTC, formatted as a string.
    - `unixtime`: Approximate time this video started as a Unix timestamp.
    length: Length of the video in seconds, including `config.VIDEO_PADDING`.
    - `extra_info`: The string from the `PlaylistEntry.info` attribute.

    Note that the `time` and `unixtime` values for objects after the first are
    estimates, due to variances in stream delivery.
    """

    def iter_playlist(
        list_sub, index_sub
    ) -> Generator[Tuple[int, PlaylistEntry], None, None]:
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
    start_time = datetime.datetime.now(datetime.timezone.utc)
    current_time = datetime.datetime.now(datetime.timezone.utc)

    # total_duration is the cumulative duration of all videos added so
    # far and is checked against config.SCHEDULE_UPCOMING_LENGTH.
    total_duration = 0

    # stream_duration is copied from stats.stream_time_remaining and used
    # to determine automatic restarts from config.STREAM_TIME_BEFORE_RESTART.
    stream_duration = stats.stream_time_remaining

    # coming_up_next is a deque of PlaylistEntry objects starting with the
    # current video up to the amount of videos defined by the limits
    # config.SCHEDULE_MAX_VIDEOS and config.SCHEDULE_UPCOMING_LENGTH.
    # coming_up_next_json is a list containing info extracted from the
    # PlaylistEntry objects.
    coming_up_next = deque()
    coming_up_next_json = []

    # If the first video in the schedule is starting after 0,
    # check against config.REWIND_LENGTH.
    if stats.elapsed_time < config.REWIND_LENGTH:
        stats.elapsed_time = 0

    # Do not include skipped video runtime in timestamp calculation
    # after the first video. This is 0 in most cases.
    length_offset = -stats.elapsed_time

    # Add extra entries before currently playing video.
    for entry in extra_entries:
        if entry.type != "extra":
            continue
        else:
            coming_up_next_json.append(
                {
                    "type": "extra",
                    "name": "",
                    "time": "",
                    "unixtime": 0,
                    "length": 0,
                    "extra_info": entry.info,
                }
            )

    # First entry is the video playing now and is added unconditionally.
    entry = playlist[entry_index]
    entry_length = get_length(entry[1])
    coming_up_next_json.append(
        {
            "type": "normal",
            "name": entry[1].name,
            "time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "unixtime": start_time.timestamp(),
            "length": entry_length,
            "extra_info": entry[1].info,
        }
    )

    entry_length += length_offset + config.VIDEO_PADDING
    if stream_duration >= config.STREAM_TIME_BEFORE_RESTART:
        length_offset = get_stream_restart_duration()
        stream_duration = 0
    else:
        length_offset = 0

    total_duration += entry_length
    stream_duration += entry_length

    # Advance timestamp for next entry by combined length and offset of previous file.
    current_time = current_time + datetime.timedelta(seconds=entry_length)

    sub_playlist = iter_playlist(playlist, entry_index)
    entry = next(sub_playlist)

    skipped_normal_entries = 0
    for entry in sub_playlist:
        # Break when the number of minimum entries is reached and either entry or
        # duration limit is reached. Entries that were skipped for matching
        # SCHEDULE_EXCLUDE_FILE_PATTERN are not counted.
        if (
            len([i for i in coming_up_next if i.type == "normal"])
            >= config.SCHEDULE_MIN_VIDEOS
        ):
            if len([i for i in coming_up_next if i.type == "normal"]) >= (
                config.SCHEDULE_MAX_VIDEOS + skipped_normal_entries
            ):
                print2(
                    "verbose",
                    "SCHEDULE_MAX_VIDEOS reached.",
                )
                break
            elif total_duration > config.SCHEDULE_UPCOMING_LENGTH:
                print2(
                    "verbose",
                    "SCHEDULE_UPCOMING_LENGTH reached.",
                )
                break

        if entry[1].type == "blank":
            continue

        else:
            # In the event of a stream restart, the value returned by
            # get_stream_restart_duration() is added to length_offset and added
            # to the next normal entry.
            if entry[1].type == "normal":
                if check_file(entry[1].path, entry[0], no_exit=True):
                    try:
                        entry_length = get_length(entry[1])
                        coming_up_next.append(entry[1])
                    except FileNotFoundError:
                        print2(
                            "error",
                            f"Line {entry[0]}. {entry[1].path} cannot be found. Not adding to schedule.",
                        )
                        continue
                    except IndexError:
                        print2(
                            "error",
                            f"Line {entry[0]}. {entry[1].path} contains no video tracks. Not adding to schedule.",
                        )
                        continue
                    except Exception as e:
                        print2(
                            "error",
                            f"Line {entry[0]}. {entry[1].path} failed: {e}. Not adding to schedule.",
                        )
                        continue
                else:
                    print2(
                        "error",
                        f"Line {entry[0]}. {entry[1].path} cannot be found. Not adding to schedule.",
                    )
                    continue

                # If name begins with any strings in SCHEDULE_EXCLUDE_FILE_PATTERN,
                # do not add them to the schedule, but calculate their lengths and
                # add to length_offset.
                if config.SCHEDULE_EXCLUDE_FILE_PATTERN is not None and entry[
                    1
                ].name.casefold().startswith(config.SCHEDULE_EXCLUDE_FILE_PATTERN):
                    print2(
                        "verbose",
                        f"Not adding entry {entry[0]}. {entry[1].name} to schedule: Name matches SCHEDULE_EXCLUDE_FILE_PATTERN.",
                    )
                    entry_length += config.VIDEO_PADDING
                    length_offset += entry_length
                    total_duration += entry_length
                    stream_duration += entry_length

                    # Advance timestamp for next entry by length of excluded file.
                    current_time = current_time + datetime.timedelta(
                        seconds=length_offset
                    )
                    skipped_normal_entries += 1
                    continue

                # If this video would run over config.STREAM_TIME_BEFORE_RESTART,
                # simulate a stream restart and add its length to length_offset before
                # calculating next timestamp.
                if (
                    stream_duration + entry_length + config.VIDEO_PADDING
                    >= config.STREAM_TIME_BEFORE_RESTART
                ):
                    length_offset = get_stream_restart_duration()
                    stream_duration = 0
                else:
                    length_offset = 0
                current_time = current_time + datetime.timedelta(seconds=length_offset)

                coming_up_next_json.append(
                    {
                        "type": "normal",
                        "name": entry[1].name,
                        "time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "unixtime": current_time.timestamp(),
                        "length": entry_length,
                        "extra_info": entry[1].info,
                    }
                )
                print2(
                    "verbose",
                    f"Added normal entry {entry[0]}. {entry[1].name} to the schedule file.",
                )

                entry_length += config.VIDEO_PADDING
                total_duration += entry_length
                stream_duration += entry_length

                current_time = current_time + datetime.timedelta(seconds=entry_length)

            elif entry[1].type == "extra":
                coming_up_next.append(entry[1])
                coming_up_next_json.append(
                    {
                        "type": "extra",
                        "name": "",
                        "time": "",
                        "unixtime": 0,
                        "length": 0,
                        "extra_info": entry[1].info,
                    }
                )
                print2(
                    "verbose",
                    f"Added extra entry {entry[0]}. {entry[1].name} to the schedule file.",
                )

            elif entry[1].type == "command":
                coming_up_next.append(entry[1])
                if entry[1].info == "RESTART":
                    length_offset = get_stream_restart_duration()
                elif entry[1].info == "INSTANT_RESTART":
                    length_offset = config.STREAM_RESTART_WAIT
                elif (
                    entry[1].info.startswith("MAIL")
                    and entry[1].info.split(" ")[0] == "MAIL"
                ):
                    continue
                elif entry[1].info == "STOP":
                    break
                elif entry[1].info == "EXCEPTION":
                    continue
                else:
                    print2(
                        "error",
                        f"Line {entry[0]}: Playlist directive {entry[1].info} not recognized.",
                    )
                    raise ValueError("Unrecognized command entry.")

            else:
                print2("warn", f"Line {entry[0]}: Invalid entry. Skipping.")

    if (
        stats.previous_files is not None
        and not ignore_previous_files
        and len(stats.recent_playlist)
    ):
        # When the program starts, recent_playlist will be empty.
        print2("verbose", "Updating previous_files array.")

        # If the current video is the same as the most recent entry in previous_files
        # (as can happen when encoding restarts due to an error), do not change the
        # previous_files deque.
        if (
            len(stats.previous_files) == 0
            or stats.previous_files[-1] != stats.recent_playlist[0]
        ):
            # Pop left from recent_playlist and append until a normal entry is added.
            while stats.recent_playlist[0]["type"] != "normal":
                stats.previous_files.append(stats.recent_playlist.popleft())
                print2(
                    "verbose",
                    f"Added {stats.previous_files[-1]['type']} entry {stats.previous_files[-1]['name']} to the previous_files array.",
                )
            stats.previous_files.append(stats.recent_playlist.popleft())
            print2(
                "verbose",
                f"Added {stats.previous_files[-1]['name']} to the previous_files array.",
            )

            # If combined length of previous_files exceeds SCHEDULE_PREVIOUS_LENGTH,
            # or number of videos exceeds SCHEDULE_PREVIOUS_MAX_VIDEOS, prune
            # previous_files.
            total_normal_previous_files = sum(
                [i["type"] == "normal" for i in stats.previous_files]
            )
            while total_normal_previous_files > config.SCHEDULE_PREVIOUS_MAX_VIDEOS:
                while stats.previous_files[0]["type"] != "normal":
                    stats.previous_files.popleft()
                stats.previous_files.popleft()
                total_normal_previous_files -= 1

            if total_normal_previous_files > config.SCHEDULE_PREVIOUS_MIN_VIDEOS:
                if config.SCHEDULE_PREVIOUS_PRUNE_TIGHT:
                    files_to_prune = 0
                else:
                    files_to_prune = -1
                for i in stats.previous_files:
                    if int(i["unixtime"]) == 0:
                        continue

                    entry_timestamp = datetime.datetime.fromtimestamp(
                        i["unixtime"], tz=datetime.timezone.utc
                    )
                    previous_time_difference = int(
                        (start_time - entry_timestamp).total_seconds()
                    )
                    print2(
                        "verbose",
                        f"Schedule generation start time: {int(start_time.timestamp())} ({start_time.strftime('%Y-%m-%d %H:%M:%S')}). {i['name']} start time: {int(entry_timestamp.timestamp())} ({entry_timestamp.strftime('%Y-%m-%d %H:%M:%S')}).",
                    )
                    print2(
                        "verbose",
                        f"Previous time difference: {str(datetime.timedelta(seconds=previous_time_difference))}.",
                    )
                    if (
                        previous_time_difference > config.SCHEDULE_PREVIOUS_LENGTH
                        and len(stats.previous_files) - files_to_prune
                        > config.SCHEDULE_PREVIOUS_MIN_VIDEOS
                    ):
                        files_to_prune += 1
                        print2("verbose", f"{files_to_prune} file(s) to prune.")
                    else:
                        break

                while (
                    total_normal_previous_files > config.SCHEDULE_PREVIOUS_MIN_VIDEOS
                    and files_to_prune > 0
                ):
                    pop = stats.previous_files.popleft()
                    print2("verbose", f"Removed {pop['name']} from previous_files.")
                    if pop["type"] == "normal":
                        files_to_prune -= 1
                        total_normal_previous_files -= 1

    elif ignore_previous_files:
        print2("verbose", "Not updating previous_files.")

    stats.recent_playlist = deque(coming_up_next_json.copy())

    schedule_json_out = {
        "program_start_time": stats.program_start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "video_start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "offset_time": config.SCHEDULE_OFFSET,
        "coming_up_next": list(coming_up_next_json),
        "previous_files": list(stats.previous_files),
        "script_version": config.SCRIPT_VERSION,
    }

    print2("verbose", "Schedule generation finished.")

    try:
        print2("verbose", "Writing schedule file.")
        with open(config.SCHEDULE_PATH, "w+") as schedule_json:
            schedule_json.write(json.dumps(schedule_json_out))
            print2("verbose", f"Wrote schedule file to {config.SCHEDULE_PATH}.")
    except OSError as e:
        print2("error", f"Error writing schedule file to {config.SCHEDULE_PATH}: {e}.")
        return

    if config.REMOTE_ADDRESS is not None:
        print2(
            "verbose",
            f"Uploading {config.SCHEDULE_PATH} to SSH server {config.REMOTE_ADDRESS}.",
        )
        upload_attempts_remaining = config.REMOTE_UPLOAD_ATTEMPTS
        sleep_event = threading.Event()

        if upload_attempts_remaining < 0:
            upload_attempts_string = ""

        while upload_attempts_remaining != 0:
            if upload_attempts_remaining > 0:
                upload_attempts_remaining -= 1
                if upload_attempts_remaining > 1:
                    upload_attempts_string = (
                        f"{upload_attempts_remaining} attempts remaining."
                    )
                else:
                    upload_attempts_string = "1 attempt remaining."

            err = None
            try:
                err = upload_ssh().result(timeout=10)
                if err is None:
                    print2("verbose", "SSH upload successful.")
                    break
                else:
                    raise err
            except TimeoutError:
                print2("error", "SSH upload timed out.")
            except Exception as e:
                print2("error", f"SSH upload failed: {e}")
            finally:
                if err is not None:
                    if upload_attempts_remaining != 0:
                        print2(
                            "error",
                            f"{upload_attempts_string} Retrying in {config.REMOTE_RETRY_PERIOD} seconds...",
                        )
                        sleep_event.wait(timeout=config.REMOTE_RETRY_PERIOD)
                        continue
                    else:
                        print2(
                            "error",
                            f"SSH upload failed after {config.REMOTE_UPLOAD_ATTEMPTS} attempts. Skipping SSH upload for this video.",
                        )


@concurrent.thread
def upload_ssh():
    """Upload JSON file to a publicly accessible location using
    fabric.
    """

    with fabric.Connection(
        config.REMOTE_ADDRESS,
        user=config.REMOTE_USERNAME,
        port=config.REMOTE_PORT,
        connect_timeout=10,
        connect_kwargs={
            "password": config.REMOTE_PASSWORD,
            "key_filename": config.REMOTE_KEY_FILE,
            "passphrase": config.REMOTE_KEY_FILE_PASSWORD,
        },
    ) as client:
        client.put(config.SCHEDULE_PATH, config.REMOTE_DIRECTORY)


@concurrent.thread
def write_index(play_index, stats):
    """Write play_index and elapsed time to play_index.txt at the period set by
    `config.TIME_RECORD_INTERVAL`. A `StreamStats` object is used to track
    elapsed time.
    """

    with open(config.PLAY_INDEX_FILE, "w") as index_file:
        index_file.write(f"{play_index}\n{stats.elapsed_time}")


if __name__ == "__main__":
    print("Run python3 main.py to start this program.")
