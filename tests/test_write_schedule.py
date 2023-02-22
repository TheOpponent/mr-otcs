def test_write_schedule(monkeypatch):

    monkeypatch.setattr("sys.argv", ["main.py", "./tests/test_config.ini"])

    import json
    import math

    import config
    from playlist import PlaylistTestEntry, StreamStats, write_schedule

    stats = StreamStats()

    config.STREAM_URL = "localhost"
    config.SCHEDULE_PATH = "tests/test_schedule.json"
    config.ALT_NAMES = {"Test file 4": "Replacement occurs on test file 4"}
    config.VIDEO_PADDING = 0
    config.STREAM_TIME_BEFORE_RESTART = 3600
    config.STREAM_RESTART_WAIT = 420
    config.SCHEDULE_EXCLUDE_FILE_PATTERN = "Test file 7".casefold()
    config.SCHEDULE_PREVIOUS_MAX_VIDEOS = 1
    config.SCHEDULE_MAX_VIDEOS = 6
    config.VERBOSE = True

    test_playlist = [
        (1,PlaylistTestEntry("Test file 1.mp4",length=1000)),
        (2,PlaylistTestEntry(":Comment 1")),
        (3,PlaylistTestEntry("Test file 2.mp4",length=360)),
        (4,PlaylistTestEntry("Test file 3.mp4 :Extra info from inline comment",length=180)),
        (5,PlaylistTestEntry("Test file 4.mp4",length=270)),
        (6,PlaylistTestEntry("Test file 5.mp4",length=720)),
        (7,PlaylistTestEntry(":Comment 2")),
        (8,PlaylistTestEntry(":Comment 3")),
        (9,PlaylistTestEntry("Test file 6.mp4",length=30)),
        (10,PlaylistTestEntry("Test file 7.mp4",length=100)),
        (11,PlaylistTestEntry("%RESTART")),
        (12,PlaylistTestEntry("Test file 8.mp4",length=180)),
        (13,PlaylistTestEntry("Test file 9.mp4",length=270))
        ]

    # test_playlist = [
    #     (0,PlaylistTestEntry("Sample Video Title #6.mp4 :(Premiere)",length=6399)),
    #     (1,PlaylistTestEntry("Sample Video Title #1.mp4",length=971)),
    #     (2,PlaylistTestEntry("Sample Video Title #2.mp4 :Extra info from inline comment",length=360)),
    #     (3,PlaylistTestEntry(":Programming Block #1")),
    #     (4,PlaylistTestEntry("Sample Video Title #3",length=2835)),
    #     (5,PlaylistTestEntry("Sample Video Title #4 :(Rerun)",length=1810)),
    #     (6,PlaylistTestEntry(":Programming Block #2")),
    #     (7,PlaylistTestEntry("Sample Video Title #5.mp4 :(Rerun)",length=2528)),
    #     (8,PlaylistTestEntry("Sample Video Title #6.mp4",length=6399))
    # ]

    for new_entry in test_playlist:
        if new_entry[1].type == "normal" and new_entry[1].name in config.ALT_NAMES:
            if isinstance(config.ALT_NAMES[new_entry[1].name],str):
                new_entry[1].name = config.ALT_NAMES[new_entry[1].name]

    index = 0
    extra_entries = []
    for i in test_playlist:
        if index == 6:
            break
        if i[1].type == "normal":
            write_schedule(test_playlist,index,stats,extra_entries=extra_entries).result()
            extra_entries = []
        elif i[1].type == "extra":
            extra_entries.append(i[1])

        index += 1

    with open(config.SCHEDULE_PATH,"r") as json_test_file:
        json_test = json.load(json_test_file)

    # Timestamps of previous_files entries will be inaccurate.
    assert json_test["coming_up_next"][0]["type"] == "normal"
    assert json_test["coming_up_next"][0]["name"] == "Test file 5"
    assert json_test["coming_up_next"][0]["length"] == 720
    assert json_test["coming_up_next"][1]["type"] == "extra"
    assert json_test["coming_up_next"][1]["extra_info"] == "Comment 2"
    assert json_test["coming_up_next"][2]["type"] == "extra"
    assert json_test["coming_up_next"][2]["extra_info"] == "Comment 3"
    assert json_test["coming_up_next"][3]["type"] == "normal"
    assert json_test["coming_up_next"][3]["name"] == "Test file 6"
    assert math.floor(json_test["coming_up_next"][3]["unixtime"]) == json_test["coming_up_next"][0]["length"] + math.floor(json_test["coming_up_next"][0]["unixtime"])
    assert json_test["coming_up_next"][3]["length"] == 30
    assert json_test["coming_up_next"][4]["type"] == "normal"
    assert json_test["coming_up_next"][4]["name"] == "Test file 8"
    assert math.floor(json_test["coming_up_next"][4]["unixtime"]) == json_test["coming_up_next"][3]["length"] + test_playlist[9][1].length + math.floor(json_test["coming_up_next"][3]["unixtime"])
    assert json_test["coming_up_next"][4]["length"] == 180
    assert json_test["coming_up_next"][5]["type"] == "normal"
    assert json_test["coming_up_next"][5]["name"] == "Test file 9"
    assert math.floor(json_test["coming_up_next"][5]["unixtime"]) == json_test["coming_up_next"][4]["length"] + math.floor(json_test["coming_up_next"][4]["unixtime"])
    assert json_test["coming_up_next"][5]["length"] == 270
    assert json_test["coming_up_next"][6]["type"] == "normal"
    assert json_test["coming_up_next"][6]["name"] == "Test file 1"
    assert math.floor(json_test["coming_up_next"][6]["unixtime"]) == json_test["coming_up_next"][5]["length"] + math.floor(json_test["coming_up_next"][5]["unixtime"])
    assert json_test["coming_up_next"][6]["length"] == 1000
    assert json_test["coming_up_next"][7]["type"] == "extra"
    assert json_test["coming_up_next"][7]["extra_info"] == "Comment 1"
    assert json_test["coming_up_next"][8]["type"] == "normal"
    assert json_test["coming_up_next"][8]["name"] == "Test file 2"
    assert math.floor(json_test["coming_up_next"][8]["unixtime"]) == json_test["coming_up_next"][6]["length"] + math.floor(json_test["coming_up_next"][6]["unixtime"])
    assert json_test["coming_up_next"][8]["length"] == 360
    assert json_test["coming_up_next"][9]["type"] == "normal"
    assert json_test["coming_up_next"][9]["name"] == "Test file 3"
    assert math.floor(json_test["coming_up_next"][9]["unixtime"]) == json_test["coming_up_next"][8]["length"] + math.floor(json_test["coming_up_next"][8]["unixtime"])
    assert json_test["coming_up_next"][9]["length"] == 180
    assert json_test["coming_up_next"][9]["extra_info"] == "Extra info from inline comment"
    assert json_test["previous_files"][0]["type"] == "normal"
    assert json_test["previous_files"][0]["name"] == "Replacement occurs on test file 4"
    assert json_test["previous_files"][0]["length"] == 270
