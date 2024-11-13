from freezegun import freeze_time


@freeze_time("2024-01-01")
def test_write_schedule(monkeypatch):
    monkeypatch.setattr("sys.argv", ["main.py", "./tests/test_config.ini"])

    import json

    import config
    from playlist import PlaylistTestEntry, write_schedule
    from streamstats import StreamStats

    stats = StreamStats()

    config.STREAM_URL = "localhost"
    config.SCHEDULE_PATH = "tests/test_schedule.json"
    config.ALT_NAMES = {"Test file 4": "Replacement occurs on test file 4"}
    config.VIDEO_PADDING = 0
    config.STREAM_TIME_BEFORE_RESTART = 3600
    config.STREAM_RESTART_WAIT = 420
    config.SCHEDULE_EXCLUDE_FILE_PATTERN = "Test file 7".casefold()
    config.SCHEDULE_PREVIOUS_MAX_VIDEOS = 1
    config.SCHEDULE_PREVIOUS_LENGTH = 20
    config.SCHEDULE_MIN_VIDEO_LENGTH = 60

    test_playlist = [
        (1, PlaylistTestEntry("Test file 1.mp4", length=1000)),
        (2, PlaylistTestEntry(":Comment 1")),
        (3, PlaylistTestEntry("Test file 2.mp4", length=360)),
        (4, PlaylistTestEntry("Test file 3.mp4 :Extra info from inline comment", length=180)),
        (5, PlaylistTestEntry("Test file 4.mp4", length=270)),
        (6, PlaylistTestEntry("Test file 5.mp4", length=720)),
        (7, PlaylistTestEntry(":Comment 2")),
        (8, PlaylistTestEntry(":Comment 3")),
        (9, PlaylistTestEntry("Test file 6.mp4", length=30)),
        (10, PlaylistTestEntry("Test file 7.mp4", length=100)),
        (11, PlaylistTestEntry("%RESTART")),
        (12, PlaylistTestEntry("Test file 8.mp4", length=180)),
        (13, PlaylistTestEntry("Test file 9.mp4", length=270)),
    ]

    for new_entry in test_playlist:
        if new_entry[1].type == "normal" and new_entry[1].name in config.ALT_NAMES:
            if isinstance(config.ALT_NAMES[new_entry[1].name], str):
                new_entry[1].name = config.ALT_NAMES[new_entry[1].name]

    index = 0
    extra_entries = []
    write_schedule(test_playlist, index, stats, extra_entries=extra_entries).result()

    with open(config.SCHEDULE_PATH, "r", encoding="utf-8") as json_test_file:
        json_test = json.load(json_test_file)

    with open("./tests/test_schedule_reference.json", "r", encoding="utf-8") as json_test_file:
        json_test_reference = json.load(json_test_file)

    assert json_test["program_start_time"] == json_test_reference["program_start_time"]
    assert json_test["video_start_time"] == json_test_reference["video_start_time"]
    assert json_test["coming_up_next"] == json_test_reference["coming_up_next"]
    