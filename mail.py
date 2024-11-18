"""Module containing the EMailDaemon class."""

import datetime
import queue
import smtplib
import ssl
import threading
import time
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import config
from config import print2
from utils import int_to_total_time


@dataclass(order=True)
class PrioritizedItem:
    priority: int
    item: Any = field(compare=False)


class EMailDaemon:
    """A daemon that receives notification messages and queues them for
    sending as e-mail alerts."""

    def __init__(self):
        self.config = {
            "smtp_server": config.MAIL_SERVER,
            "smtp_port": config.MAIL_PORT,
            "login": config.MAIL_LOGIN,
            "password": config.MAIL_PASSWORD,
            "from_address": config.MAIL_FROM_ADDRESS,
            "to_address": config.MAIL_TO_ADDRESS,
            "use_ssl": config.MAIL_USE_SSL,
            "use_starttls": config.MAIL_USE_STARTTLS,
        }
        self.ssl_context = (
            ssl.create_default_context()
            if self.config["use_ssl"] or self.config["use_starttls"]
            else None
        )
        self.retries = 3
        self.retry_delay = 1
        self.retry_delay_max = 128
        self.queue = queue.PriorityQueue(maxsize=10)
        self.last_sent = {}
        self._lock = threading.Lock()
        self.running = True
        self.logged_in = False
        self.last_exception = None
        self.last_exception_time = datetime.datetime.now(datetime.timezone.utc)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while self.running:
            try:
                msg, alert_type, bypass_interval = self.queue.get(timeout=1).item
                if self._send_email_if_allowed(msg, alert_type, bypass_interval):
                    self.retry_delay = 1
                else:
                    # If an e-mail could not be sent, reinsert it into the queue with
                    # retry priority and try again.
                    print2(
                        "error",
                        f"Message \"{msg['Subject']}\" failed to send. Retrying in {self.retry_delay} seconds.",
                    )
                    with self._lock:
                        self.queue.put_nowait(
                            PrioritizedItem(1, (msg, alert_type, bypass_interval))
                        )
                    time.sleep(self.retry_delay)
                    self.retry_delay = min(self.retry_delay * 2, self.retry_delay_max)
                    continue
            except queue.Empty:
                pass

            time.sleep(1)

    def clear_queue(self):
        with self._lock:
            try:
                while True:
                    self.queue.get_nowait()
            except queue.Empty:
                pass

            self.last_sent = {}

    def _login(self, server, timeout=10):
        try:
            if self.config["use_ssl"]:
                server = smtplib.SMTP_SSL(
                    self.config["smtp_server"],
                    self.config["smtp_port"],
                    self.ssl_context,
                    timeout=timeout,
                )
            else:
                server = smtplib.SMTP(
                    self.config["smtp_server"],
                    self.config["smtp_port"],
                    timeout=timeout,
                )

                if self.config["use_starttls"]:
                    server.starttls(context=self.ssl_context)
            server.login(self.config["login"], self.config["password"])
            return server
        except Exception as e:
            raise e

    def _send_email_if_allowed(
        self, msg: MIMEMultipart, alert_type: str, bypass_interval: bool
    ):
        """Sends an e-mail message.

        Messages of a given `alert_type` are sent only once every hour
        and further messages of the same type within that period are
        discarded, unless `bypass_interval` is True. Returns True if
        the message is sent successfully or was discarded for that
        reason, False otherwise.
        """

        current_time = datetime.datetime.now(datetime.timezone.utc)

        with self._lock:
            last_sent_time: datetime.datetime = self.last_sent.get(
                alert_type, datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
            )
            if bypass_interval or (
                current_time - last_sent_time >= datetime.timedelta(hours=1)
            ):
                sent = self._send_email(msg)
                if sent:
                    # Add extra delay time for alert_type "schedule_error"
                    # to reduce the amount of redundant messages when
                    # multiple schedules are generated in a short time with
                    # the same faulty files. The extra time is the maximum
                    # length of a schedule, minus 1 hour, but not less than
                    # 0.
                    if alert_type != "schedule_error":
                        self.last_sent[alert_type] = current_time
                    else:
                        self.last_sent["schedule_error"] = (
                            current_time
                            + datetime.timedelta(
                                minutes=max(0, config.SCHEDULE_UPCOMING_LENGTH - 60)
                            )
                        )
                    return True
                return False
            print2(
                "notice",
                f"Alert {alert_type} not sent: Less than 1 hour since last alert was sent ({last_sent_time.astimezone().strftime('%Y-%m-%d %H:%M:%S')}).",
            )
            return True

    def _send_email(self, msg: MIMEMultipart, timeout=10):
        """Returns True if the e-mail was sent successfully, False if
        an error occurred.
        """

        server = None

        # If the login test on program startup failed, try to log in again.
        if not self.logged_in:
            test_result = self.test_login()
            if not test_result:
                return False

        retries = self.retries
        while retries > 0:
            try:
                server = self._login(server, timeout)
                server.sendmail(
                    self.config["from_address"],
                    self.config["to_address"],
                    msg.as_string(),
                )
                print2("verbose", f"Sent e-mail: \"{msg['Subject']}\"")
                return True
            except (
                smtplib.SMTPAuthenticationError,
                smtplib.SMTPNotSupportedError,
            ) as e:
                print2(
                    "error",
                    f"Failed to login to e-mail server {self.config['smtp_server']}: {e}",
                )
                print2("error", "Mail features disabled.")
                self.stop()
                return False
            except TimeoutError as e:
                print2(
                    "error",
                    f"Timed out while trying to send e-mail \"{msg['Subject']}\": {e}",
                )
                retries -= 1
                continue
            except Exception as e:
                print2("error", f"Failed to send e-mail \"{msg['Subject']}\": {e}")
                retries -= 1
                continue
            finally:
                if server is not None:
                    server.quit()

        print2(
            "error",
            f"Failed to send e-mail alert \"{msg['Subject']}\" after {self.retries} attempts.",
        )
        return False

    def add_alert(
        self, alert_type: str, message="", bypass_interval=False, urgent=False, **kwargs
    ):
        """Add an alert to be sent by e-mail. By default, alerts are
        added to a queue, to be sent 1 hour after the last e-mail of
        the same `alert_type` was sent.

        If `bypass_interval` is True, the alert will be sent regardless
        of the last time an alert of the same `alert_type` was sent.

        If `urgent` is True, the e-mail is sent immediately, bypassing
        the queue and blocking execution until it is sent.

        For playlist-related messages, the keyword arguments `line_num`
        can be given a number.

        For exception-related messages, the keyword arguments
        `exception`, `exception_time`, and `traceback` can be given an
        Exception object, a datetime object, and a string containing
        traceback information respectively. The keyword arguments
        `total_time` and `total_videos` can be given a string and int
        respectively.
        """

        if not self.running:
            print2("verbose", f"Alert {alert_type} not sent: Mail alerts are disabled.")
            return

        local_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line_num = kwargs.get("line_num")
        total_time = kwargs.get("total_time")
        total_videos = kwargs.get("total_videos")
        priority = 0

        if exception := kwargs.get("exception"):
            exception_name = type(exception).__name__
            exception_string = f"{exception_name}: {str(exception)}"
            traceback_string = kwargs.get("traceback", "")
        else:
            exception_name = ""
            exception_string = ""
            traceback_string = ""
        if exception_time := kwargs.get("exception_time"):
            exception_timestamp = exception_time.strftime("%Y-%m-%d %H:%M:%S")
            downtime_length = int_to_total_time(datetime.datetime.now(datetime.timezone.utc) - exception_time)
        else:
            exception_timestamp = ""
            downtime_length = ""

        # Priority list:
        # 0: Urgent, send before all other messages
        # 1: Retried message
        # 10: Normal priority
        alert_types = {
            "stream_down": (
                0,
                "Stream offline",
                f'The stream went offline due to the error "{exception_name}" at {exception_timestamp}.\n\nBefore this error, not including restarts, the stream ran for {total_time}{f" and played {total_videos} videos" if total_videos is not None else ""}.\n\nException details:\n{exception_string}',
            ),
            "stream_resume": (
                10,
                "Stream resumed",
                (
                    f'The stream reconnected at {local_time}. It recovered from the error "{exception_name}", which occurred at {exception_timestamp}. The stream was offline for {downtime_length}.\n\nException details:\n{exception_string}'
                    if exception and exception_time
                    else f"The stream reconnected at {local_time}. It was offline for {downtime_length}."
                ),
            ),
            "file_retry": (
                0,
                f"Video {message} not found - Now retrying infinitely",
                f"The video {message} {f'on playlist line {line_num} ' if line_num is not None else ''}could not be found at {local_time}. Because RETRY_ATTEMPTS is -1, it is currently retrying before the stream resumes.\n\nWarning: Due to the nature of this error, it is likely that more files in the playlist are also missing. Check {config.BASE_PATH}.",
            ),
            "file_not_found": (
                0,
                f"Video {message} not found - Skipping in schedule",
                f"The video {message} {f'on playlist line {line_num} ' if line_num is not None else ''}could not be found at {local_time}. The video has been skipped.\n\nWarning: Due to the nature of this error, it is likely that more files in the playlist are also missing. Check {config.BASE_PATH}.",
            ),
            "schedule_error": (
                0,
                "Errors generating the schedule",
                f"The following errors occurred when generating the schedule, causing videos to be skipped:\n{message}",
            ),
            "program_error": (
                0,
                "Program error",
                f"Mr. OTCS exited at {exception_timestamp} due to an unrecoverable error: {exception_string}\n\nMr. OTCS ran for {total_time}{f' and played {total_videos} videos' if total_videos is not None else ''}."
                + f"\n\n{traceback_string}"
                if traceback_string != ""
                else "",
            ),
            "remote_success_after_error": (
                0,
                "Schedule upload succeeded with errors",
                f"The schedule file upload to {config.REMOTE_ADDRESS} succeeded, but the following errors occurred:\n{message}",
            ),
            "remote_error": (
                0,
                "Schedule upload failed",
                f"The following errors occurred while trying to upload the schedule file to {config.REMOTE_ADDRESS}:\n{message}",
            ),
            "remote_auth_failed": (
                0,
                "Schedule uploads disabled after authentication failure",
                f"Authentication to {config.REMOTE_ADDRESS} failed, and remote uploading of the schedule file has been disabled. Reason:\n{message}",
            ),
            "playlist_loop": (
                10,
                "Playlist looped",
                f"The playlist looped at {local_time}.",
            ),
            "playlist_stop": (
                0,
                "Playlist stopped",
                f"The playlist reached a %STOP command on line {line_num} at {local_time}, and Mr. OTCS has exited.\n\nMr. OTCS ran for {total_time}{f' and played {total_videos} videos' if total_videos is not None else ''}.",
            ),
            "playlist_end": (
                0,
                "Playlist ended",
                f"The playlist reached the end at {local_time}, and Mr. OTCS has exited.\n\nMr. OTCS ran for {total_time}{f' and played {total_videos} videos' if total_videos is not None else ''}.",
            ),
            "mail_command": (
                10,
                f"%MAIL command: {message[:50]}" if message else "%MAIL command",
                f"The playlist reached a %MAIL command on line {line_num} at {local_time}."
                + (f" The message is:\n\n{message}" if message else ""),
            ),
            "new_version": (
                10,
                f"New version available: {kwargs.get('version')}",
                (
                    f"A new version of Mr. OTCS is available: {kwargs.get('version')}\n"
                    f"The new version can be found at {kwargs.get('url')}.\n\n"
                    f"Release notes:\n\n{message}"
                ),
            ),
            "status_report": (
                10,
                "Status report",
                "This is the regular Mr. OTCS status report.\n\n" + message,
            ),
            "general": (10, "General message", message),
        }

        if alert_type in alert_types:
            priority, subject, body = alert_types[alert_type]
            body += f"\n\n\nGenerated by Mr. OTCS version {config.SCRIPT_VERSION}."

            msg = MIMEMultipart()
            msg["From"] = self.config["from_address"]
            msg["To"] = self.config["to_address"]
            msg["Subject"] = f"[{config.MAIL_PROGRAM_NAME}] {subject}"
            msg.attach(MIMEText(body, "plain"))

            if config.MAIL_ALERT_HIGH_PRIORITY_ERROR and alert_type in [
                "stream_down",
                "file_retry",
                "file_not_found",
                "schedule_error",
                "program_error",
                "remote_success_after_error",
                "remote_error",
                "remote_auth_failed",
            ]:
                msg["Importance"] = "High"
                msg["X-MSMail-Priority"] = "High"
                msg["X-Priority"] = "1"

            if not urgent:
                print2(
                    "verbose",
                    f"Adding e-mail alert type {alert_type} with priority {priority} to queue:",
                )
                print2("verbose", f"Subject: [{config.MAIL_PROGRAM_NAME}] {subject}")
                print2("verbose", body)
                try:
                    with self._lock:
                        self.queue.put_nowait(
                            PrioritizedItem(
                                priority, (msg, alert_type, bypass_interval)
                            )
                        )
                except queue.Full:
                    print2(
                        "error",
                        f"E-mail alert queue is full. Message \"{msg['Subject']}\" discarded.",
                    )
            else:
                print2("verbose", f"Sending urgent e-mail alert type {alert_type}:")
                print2("verbose", f"Subject: [{config.MAIL_PROGRAM_NAME}] {subject}")
                print2("verbose", body)
                with self._lock:
                    sent = self._send_email(msg)
                    if sent:
                        self.last_sent[alert_type] = datetime.datetime.now(
                            datetime.timezone.utc
                        )
        else:
            raise ValueError(f"Unrecognized alert type: {alert_type}")

    def test_login(self, timeout=10, retries=3):
        """Log in to the mail server and immediately exit."""

        server = None

        retries = self.retries
        while retries > 0:
            try:
                server = self._login(server, timeout)
                self.logged_in = True
                return True
            except (
                smtplib.SMTPAuthenticationError,
                smtplib.SMTPNotSupportedError,
            ) as e:
                print2(
                    "error",
                    f"Failed to login to e-mail server {self.config['smtp_server']}: {e}",
                )
                print2("error", "Mail features disabled.")
                self.stop()
                return False
            except TimeoutError:
                print2(
                    "error",
                    "Timed out while trying to login.",
                )
                retries -= 1
                continue
            except Exception as e:
                print2("error", f"Failed to login: {e}")
                retries -= 1
                continue
            finally:
                if server is not None:
                    server.quit()

        print2(
            "error",
            f"Login test to e-mail server {self.config['smtp_server']} failed after {self.retries} attempts. Will retry upon next mail alert.",
        )
        return False

    def stop(self):
        self.running = False
        self.clear_queue()
        self.thread.join()


if __name__ == "__main__":
    print("Run python3 main.py to start this program.")
