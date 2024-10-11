import threading
import time
import ssl
import smtplib
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import queue

import config
from config import print2
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class PrioritizedItem:
    priority: int
    item: Any = field(compare=False)


class EMailDaemon:
    """A daemon that receives notification messages and queues them for
    sending as e-mail alerts."""

    def __init__(self):
        self.smtp_server = config.MAIL_SERVER
        self.smtp_port = config.MAIL_PORT
        self.login = config.MAIL_LOGIN
        self.password = config.MAIL_PASSWORD
        self.from_address = config.MAIL_FROM_ADDRESS
        self.to_address = config.MAIL_TO_ADDRESS
        self.use_ssl = config.MAIL_USE_SSL
        self.use_starttls = config.MAIL_USE_STARTTLS
        self.ssl_context = (
            ssl.create_default_context() if self.use_ssl or self.use_starttls else None
        )
        self.retries = 3
        self.retry_delay = 5
        self.queue = queue.PriorityQueue(maxsize=10)
        self.last_sent = {}
        self._lock = threading.Lock()
        self.running = True
        self.logged_in = False
        self.last_exception = None
        self.last_exception_time = datetime.datetime.now()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while self.running:
            try:
                msg, alert_type, bypass_interval = self.queue.get(timeout=1).item
                if not self._send_email_if_allowed(msg, alert_type, bypass_interval):
                    # If an e-mail could not be sent, reinsert it into the queue with
                    # retry priority and try again.
                    # TODO: Implement backoff
                    with self._lock:
                        self.queue.put_nowait(
                            PrioritizedItem(
                                1, (msg, alert_type, bypass_interval)
                            )
                        )
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
            if self.use_ssl:
                server = smtplib.SMTP_SSL(
                    self.smtp_server, self.smtp_port, self.ssl_context, timeout=timeout
                )
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=timeout)

                if self.use_starttls:
                    server.starttls(context=self.ssl_context)
            server.login(self.login, self.password)
            return server
        except Exception as e:
            raise e

    def _send_email_if_allowed(self, msg: MIMEMultipart, alert_type: str, bypass_interval: bool):
        """Sends an e-mail message.
        
        Messages of a given type are sent only once every 60 minutes
        and further messages of the same type within that period are
        discarded, unless `bypass_interval` is True. Returns True if
        the message is sent successfully or was discarded for that 
        reason, False otherwise.
        """

        current_time = datetime.datetime.now()

        with self._lock:
            last_sent_time = self.last_sent.get(alert_type, datetime.datetime.min)
            if bypass_interval or (
                current_time - last_sent_time >= datetime.timedelta(hours=1)
            ):
                sent = self._send_email(msg)
                if sent:
                    self.last_sent[alert_type] = current_time
                    time.sleep(5)
                    return True
                else:
                    return False
            else:
                print2(
                    "verbose",
                    f"Alert {alert_type} not sent: Less than 1 hour since last alert was sent ({last_sent_time.strftime('%Y-%m-%d %H:%M:%S')}).",
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
                server.sendmail(self.from_address, self.to_address, msg.as_string())
                print2("verbose", f"Sent e-mail: \"{msg['Subject']}\"")
                return True
            except (
                smtplib.SMTPAuthenticationError,
                smtplib.SMTPNotSupportedError,
            ) as e:
                print2(
                    "error", f"Failed to login to e-mail server {self.smtp_server}: {e}"
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

        If `bypass_interval` is True, the alert will be sent as soon as
        possible, ignoring the last time an alert of the same
        `alert_type` was sent.

        If `urgent` is True, the e-mail is sent immediately, bypassing
        the queue and blocking execution until it is sent.

        For playlist-related messages, the keyword argument `line_num`
        can be given a number.

        For exception-related messages, the keyword arguments
        `exception` and `exception_time` can be given an Exception
        object and a datetime object respectively. The keyword argument
        `total_time` can be given a string.
        """

        if not self.running:
            print2("verbose", f"Alert {alert_type} not sent: Mail alerts are disabled.")
            return

        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line_num = kwargs.get("line_num")
        total_time = kwargs.get("total_time")
        priority = 0

        if exception := kwargs.get("exception"):
            exception_string = f"{type(exception).__name__}: {str(exception)}"
        else:
            exception_string = ""
        if exception_time := kwargs.get("exception_time"):
            exception_time = kwargs.get("exception_time").strftime("%Y-%m-%d %H:%M:%S")

        # Priority list:
        # 0: Urgent, send before all other messages
        # 1: Retried message
        # 10: Normal priority
        alert_types = {
            "stream_down": (
                0,
                "Stream offline",
                f'The stream went offline due to exception "{exception_string}" at {exception_time}.',
            ),
            "stream_resume": (
                10,
                "Stream resumed",
                (
                    f'The stream reconnected at {current_time}. It recovered from the exception "{exception_string}", which occurred at {exception_time}.'
                    if exception and exception_time
                    else f"The stream reconnected at {current_time}."
                ),
            ),
            "program_error": (
                0,
                "Program error",
                f"Mr. OTCS exited at {exception_time} due to an unrecoverable error: {exception_string}\n\nMr. OTCS ran for {total_time}.",
            ),
            "playlist_loop": (
                10,
                "Playlist looped",
                f"The playlist looped at {current_time}.",
            ),
            "playlist_stop": (
                0,
                "Playlist stopped",
                f"The playlist reached a %STOP command on line {line_num} at {current_time}, and Mr. OTCS has exited.",
            ),
            "playlist_end": (
                0,
                "Playlist ended",
                f"The playlist reached the end at {current_time}, and Mr. OTCS has exited.",
            ),
            "mail_command": (
                10,
                f"%MAIL command: {message[:50]}" if message else "%MAIL command",
                f"The playlist reached a %MAIL command on line {line_num} at {current_time}."
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
            msg = MIMEMultipart()
            msg["From"] = self.from_address
            msg["To"] = self.to_address
            msg["Subject"] = f"[{config.MAIL_PROGRAM_NAME}] {subject}"
            msg.attach(MIMEText(body, "plain"))

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
                        self.last_sent[alert_type] = datetime.datetime.now()
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
                    "error", f"Failed to login to e-mail server {self.smtp_server}: {e}"
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
            f"Login test to e-mail server {self.smtp_server} failed after {self.retries} attempts. Will retry upon next mail alert.",
        )
        return False

    def stop(self):
        self.running = False
        self.clear_queue()
        self.thread.join()


if __name__ == "__main__":
    print("Run python3 main.py to start this program.")
