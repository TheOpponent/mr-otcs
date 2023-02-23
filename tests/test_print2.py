def test_print2_functions(monkeypatch,capsys):

    monkeypatch.setattr("sys.argv", ["main.py", "./tests/test_config.ini"])
    
    import config
    from config import print2

    config.VERBOSE = 0b11111111

    print2("verbose2","Super Verbose message")
    capture = capsys.readouterr()
    assert capture.out == "[Info]" + " Super Verbose message\n"

    print2("verbose","Verbose message")
    capture = capsys.readouterr()
    assert capture.out == "[Info]" + " Verbose message\n"

    print2("info","Info message")
    capture = capsys.readouterr()
    assert capture.out == "[Info]" + " Info message\n"

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

    config.VERBOSE = 0

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