"""Helper functions."""

import datetime

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
