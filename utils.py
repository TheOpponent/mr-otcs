"""Helper functions."""

import datetime
import errno
import os
import time

import config
from config import print2
from streamstats import StreamStats


def int_to_time(seconds):
    """Returns a time string containing hours, minutes, and seconds
    from an amount of seconds, in the format H:MM:SS. The argument
    can be an int, float, or `datetime.timedelta` object.
    """

    if isinstance(seconds, datetime.timedelta):
        seconds = seconds.total_seconds()
    elif not isinstance(seconds, (int, float)):
        raise ValueError("Not an int, float, or datetime.timedelta object")

    hr, min = divmod(seconds, 3600)
    min, sec = divmod(min, 60)

    return f"{hr}:{min:02d}:{sec:02d}"


def int_to_total_time(seconds, round_down_zero=True):
    """Returns a plain time string containing days, hours, minutes, and
    seconds from an amount of seconds. The argument can be an int,
    float, or `datetime.timedelta` object.

    If `round_down_zero` is True, times of less than 1 second will be
    returned as "less than a second". Otherwise, returns "0 seconds".
    """

    if isinstance(seconds, datetime.timedelta):
        seconds = seconds.total_seconds()
    elif not isinstance(seconds, (int, float)):
        raise ValueError("Not an int, float, or datetime.timedelta object")

    if seconds < 1:
        return "less than a second" if round_down_zero else "0 seconds"

    days, hr = divmod(int(seconds), 86400)
    hr, min = divmod(hr, 3600)
    min, sec = divmod(min, 60)
    string = []

    if days > 0:
        string.append(f"{days} days" if days != 1 else f"{days} day")
    if hr > 0:
        string.append(f"{hr} hours" if hr != 1 else f"{hr} hour")
    if min > 0:
        string.append(f"{min} minutes" if min != 1 else f"{min} minute")
    if sec > 0:
        string.append(f"{sec} seconds" if sec != 1 else f"{sec} second")

    return ", ".join(string)


def check_file(path, line_num=None, no_exit=False, stats: StreamStats = None):
    """Retry opening nonexistent files up to `config.RETRY_ATTEMPTS`.

    If file is found, returns True.
    If `config.EXIT_ON_FILE_NOT_FOUND` is True, throw exception if
    retry attempts don't succeed. If False, return False and continue.
    `no_exit` overrides `config.EXIT_ON_FILE_NOT_FOUND`.

    `stats` is a StreamStats object that contains a running e-mail
    daemon. If not None, an e-mail alert will be sent immediately
    if a file is not found and `config.RETRY_ATTEMPTS` is -1, to inform
    the user of the start of infinite retries to find the file.
    """

    if path is None:
        return True

    retry_attempts_remaining = config.RETRY_ATTEMPTS

    # If RETRY_ATTEMPTS is -1, don't print number of attempts
    # remaining.
    retry_attempts_string = ""

    # Send an e-mail alert immediately if RETRY_ATTEMPTS is -1.
    alert_sent = False

    while not os.path.isfile(path):
        if (
            not alert_sent
            and stats is not None
            and retry_attempts_remaining < 0
            and stats.mail_daemon_running(config.MAIL_ALERT_ON_FILE_NOT_FOUND)
        ):
            alert_sent = True
            stats.mail_daemon.add_alert(
                "playlist_file_retry",
                message=path,
                line_num=line_num,
            )
        # Print number of attempts remaining.
        if retry_attempts_remaining > 0:
            if retry_attempts_remaining > 1:
                retry_attempts_string = (
                    f"{retry_attempts_remaining} attempts remaining. "
                )
            else:
                retry_attempts_string = "1 attempt remaining. "
            retry_attempts_remaining -= 1
        elif retry_attempts_remaining == 0:
            if config.EXIT_ON_FILE_NOT_FOUND and not no_exit:
                if line_num is not None:
                    print2("fatal", f"Line {line_num}: {path} not found.")
                else:
                    print2("error", f"{path} not found.")
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

            if line_num is not None:
                print2("error", f"Line {line_num}: {path} not found. Continuing.")
            else:
                print2("error", f"{path} not found. Continuing.")
            return False

        print2("error", f"File not found: {path}.")
        print2(
            "error",
            f"{retry_attempts_string}Retrying in {config.RETRY_PERIOD} seconds...",
        )

        time.sleep(config.RETRY_PERIOD)
    if (
        alert_sent
        and stats is not None
        and stats.mail_daemon_running(config.MAIL_ALERT_ON_STREAM_RESUME)
    ):
        stats.mail_daemon.add_alert("stream_resume")
    return True


if __name__ == "__main__":
    print("Run python3 main.py to start this program.")
