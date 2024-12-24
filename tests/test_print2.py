import datetime
from freezegun import freeze_time

@freeze_time("2023-01-01 00:00:00")
def test_print2_functions(monkeypatch,capsys):

    monkeypatch.setattr("sys.argv", ["main.py", "./tests/test_config.ini"])

    import config
    from config import print2

    config.VERBOSE = 0b11111111

    print2("debug","Debug message")
    capture = capsys.readouterr()
    assert capture.out == datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + '\033[90m' + "[Debug]" + '\033[0m' +" Debug message\n"

    print2("verbose2","Debug message using alias level")
    capture = capsys.readouterr()
    assert capture.out == datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + '\033[90m' + "[Debug]" + '\033[0m' +" Debug message using alias level\n"

    print2("verbose","Verbose message")
    capture = capsys.readouterr()
    assert capture.out == datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + '\033[90m' + "[Verbose]" + '\033[0m' +" Verbose message\n"

    print2("info","Info message")
    capture = capsys.readouterr()
    assert capture.out == datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + "[Info]" + " Info message\n"

    print2("play","Play message")
    capture = capsys.readouterr()
    assert capture.out == datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + '\033[92m' + "[Play]" + '\033[0m' + " Play message\n"

    print2("notice","Notice message")
    capture = capsys.readouterr()
    assert capture.out == datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + '\033[96m' + "[Notice]" + '\033[0m' + " Notice message\n"

    print2("warn","Warn message")
    capture = capsys.readouterr()
    assert capture.out == datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + '\033[93m' + "[Warn]" + '\033[0m' + " Warn message\n"

    print2("error","Error message")
    capture = capsys.readouterr()
    assert capture.out == datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + '\033[31m' + "[Error]" + '\033[0m' + " Error message\n"

    print2("fatal","Fatal message")
    capture = capsys.readouterr()
    assert capture.out == datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + '\033[31m' + "[Fatal]" + '\033[0m' + " Fatal message\n"

    config.VERBOSE = 0

    print2("debug","Debug message message")
    capture = capsys.readouterr()
    assert capture.out == ""

    print2("verbose2","Super Verbose message")
    capture = capsys.readouterr()
    assert capture.out == ""

    print2("verbose","Verbose message")
    capture = capsys.readouterr()
    assert capture.out == ""

    print2("info","Info message")
    capture = capsys.readouterr()
    assert capture.out == ""

    print2("play","Play message")
    capture = capsys.readouterr()
    assert capture.out == ""

    print2("notice","Notice message")
    capture = capsys.readouterr()
    assert capture.out == ""

    print2("warn","Warn message")
    capture = capsys.readouterr()
    assert capture.out == ""

    print2("error","Error message")
    capture = capsys.readouterr()
    assert capture.out == ""

    print2("fatal","Fatal message")
    capture = capsys.readouterr()
    assert capture.out == ""