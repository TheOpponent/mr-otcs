import config
from config import print2


def test_print2(capsys):

    config.VERBOSE = 0b1111111

    print2("verbose","Verbose message")
    capture = capsys.readouterr()
    assert capture.out == "[Info]" + '\033[0m' + " Verbose message\n"

    print2("info","Info message")
    capture = capsys.readouterr()
    assert capture.out == "[Info]" + '\033[0m' + " Info message\n"

    print2("play","Play message")
    capture = capsys.readouterr()
    assert capture.out == '\033[92m' + "[Play]" + '\033[0m' + " Play message\n"

    print2("notice","Notice message")
    capture = capsys.readouterr()
    assert capture.out == '\033[96m' + "[Notice]" + '\033[0m' + " Notice message\n"

    print2("warn","Warn message")
    capture = capsys.readouterr()
    assert capture.out == '\033[93m' + "[Warn]" + '\033[0m' + " Warn message\n"

    print2("error","Error message")
    capture = capsys.readouterr()
    assert capture.out == '\033[31m' + "[Error]" + '\033[0m' + " Error message\n"

    print2("fatal","Fatal message")
    capture = capsys.readouterr()
    assert capture.out == '\033[31m' + "[Error]" + '\033[0m' + " Fatal message\n"


def test_print2_nooutput(capsys):

    config.VERBOSE = 0

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