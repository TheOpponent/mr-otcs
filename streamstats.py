import datetime
from collections import deque
from concurrent import futures

import config
import mail


class StreamStats:
    """A singleton to store persistent information regarding the stream
    runtime and the history of the schedule, program statistics, and
    various timers.
    """

    recent_playlist: deque
    """A copy of the dict objects that were written as JSON objects on the
    most recent call to write_schedule().
    """

    previous_files: deque
    """Entries from recent_playlist are popped from the left and appended to
    this deque.
    """

    program_start_time: datetime.datetime
    "The time this program was started, in UTC."

    elapsed_time: int
    "Seconds the current video has been playing."

    videos_since_restart: int
    """Number of videos played since program start or last restart of RTMP
    process. Does not include STREAM_RESTART_BEFORE_VIDEO or
    STREAM_RESTART_AFTER_VIDEO.
    """

    total_videos: int
    """Total number of videos played to completion since program start.
    Does not include STREAM_RESTART_BEFORE_VIDEO or
    STREAM_RESTART_AFTER_VIDEO."""

    stream_start_time: datetime.datetime
    """The time the current stream was started, in UTC. Set only after
    starting the RTMP process.
    """

    stream_time_remaining: int
    "Seconds before automatic stream restart."

    video_resume_point: int
    """If video encoding is aborted, this is set to elapsed_time. This is the
    earliest time the video will be allowed to start from. After successful
    encoding, this is set to 0.
    """

    check_connection_future: futures.Future
    """A Future for the check_connection() function, to ensure only one check
    is run at a time.
    """

    schedule_future: futures.Future
    """A Future for the write_schedule() function, to ensure only one schedule
    is written at a time. If a write_schedule does not complete before the
    next video in the playlist starts, the current future is cancelled.
    """

    last_connection_check: datetime.datetime
    """The most recent internet connection check, used to help ensure checks
    are not done more often than config.CHECK_INTERVAL.
    """

    mail_daemon: mail.EMailDaemon
    """An e-mail daemon that will send e-mail alerts."""

    newest_version: str
    """The most recent version available since the last version check."""

    version_check_wait: int
    """Wait this many seconds before the next version check."""

    version_check_future: futures.Future
    """A Future for the check_new_version() function."""

    status_report_wait: int
    """Wait this many seconds before generating a status report."""

    restarts: int
    """Number of times the stream restarted normally, including stream
    duration timeouts in STREAM_TIME_BEFORE_RESTART, %RESTART and
    %INSTANT_RESTART commands, and pressing Ctrl-C.
    """

    retries: int
    """Number of times the stream was interrupted unexpectedly and
    restarted.
    """

    stream_downtime: int
    """Time in seconds that stream errors have caused downtime."""

    exceptions: list[tuple[Exception, datetime.datetime]]
    """A list of exceptions caught by the program during the main loop.
    This is a list containing tuples of the exception and the time
    they occurred.
    """

    last_exception_time: datetime.datetime
    """The time the most recent exception that caused a stream restart
    took place.
    """

    def __init__(self):
        self.recent_playlist = deque()
        if (
            config.SCHEDULE_PREVIOUS_MIN_VIDEOS >= 1
            and config.SCHEDULE_PREVIOUS_MAX_VIDEOS >= 1
            and config.SCHEDULE_PREVIOUS_LENGTH >= 1
        ):
            self.previous_files = deque()
        else:
            self.previous_files = None
        self.program_start_time = datetime.datetime.now(datetime.timezone.utc)
        self.elapsed_time = 0
        self.videos_since_restart = 0
        self.total_videos = 0
        self.stream_start_time = datetime.datetime.now(datetime.timezone.utc)
        self.stream_time_remaining = config.STREAM_TIME_BEFORE_RESTART
        self.video_resume_point = 0
        self.check_connection_future = None
        self.schedule_future = None
        self.last_connection_check = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(seconds=config.CHECK_INTERVAL)
        self.mail_daemon = None
        self.newest_version = config.SCRIPT_VERSION
        self.version_check_wait = 0
        self.version_check_future = None
        self.status_report_wait = config.MAIL_ALERT_STATUS_REPORT * 86400
        self.restarts = 0
        self.retries = 0
        self.stream_downtime = 0
        self.exceptions = []
        self.last_exception_time = datetime.datetime.now(datetime.timezone.utc)

    def rewind(self, time):
        """Subtract this many seconds from elapsed_time, without going below
        0.
        """

        self.elapsed_time = max(0, self.elapsed_time - time)

    def set_connection_check_time(self):
        """Set the last connection check time to the current time."""

        self.last_connection_check = datetime.datetime.now(datetime.timezone.utc)

    def force_connection_check(self):
        """Set the last connection check time to the current time, minus
        config.CHECK_INTERVAL, to force the next connection check to take
        place immediately."""

        self.last_connection_check = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(seconds=config.CHECK_INTERVAL)

    def update_stream_downtime(self):
        """Add the time between the last exception time and now to the
        stream downtime stat."""

        self.stream_downtime += (
            datetime.datetime.now(datetime.timezone.utc) - self.last_exception_time
        ).total_seconds()


if __name__ == "__main__":
    print("Run python3 main.py to start this program.")