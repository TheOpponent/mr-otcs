# Mr. OTCS
A script to play a list of video files in a continuous loop, transcode it to RTMP, and produce schedules based on upcoming videos in the playlist. Requires Python 3.7 or later. 

See the [wiki](https://github.com/TheOpponent/mr-otcs/wiki) for installation instructions on Raspberry Pi.

The playlist is a text file with filenames:
```
Video Name 1.mp4
Video Name 2.mp4
Video Name 3.mp4

# Comments are supported, and blank lines are ignored
Series Name/Episode 1.mp4
Series Name/Episode 2.mp4 
Series Name/Episode 3.mp4 :Entries can have metadata that will display differently

# Videos starting with certain words can be played but not included in the schedule
Commercial 1.mp4

:Lines beginning with a colon are treated as special lines that act as separators
Video Name 4.mp4 :(Rerun)
A Movie.mp4 :(Premiere)
Video Name 5.mp4
```

In its default configuration, Mr. OTCS consists of a Python script that reads this file and starts a video player (ffmpeg by default) for each video in turn, streaming it to a local RTMP server. A shell script run alongside launches an nginx server and another ffmpeg process that relays the transcoded video a third-party service. This is made possible with [ffmpeg-hls-pts-discontinuity-reclock](https://github.com/jjustman/ffmpeg-hls-pts-discontinuity-reclock), a fork of ffmpeg with support for repairing HLS discontinuities.

## Example schedule
![Example schedule](https://user-images.githubusercontent.com/8432212/116021273-def42b80-a615-11eb-96ba-3ad4d8f5375a.png)

The generated schedule runs up to a user-defined combined length of upcoming videos and/or any number of videos. The script writes an array of JavaScript objects that contain video names and timestamps for their scheduled start times. A basic HTML file is provided as a template for JSON usage, including parsing metadata in the playlist.

# Disclaimer
Use this script at your own risk. The authors assume no responsibility for any administrative action taken on streaming accounts as a result of this script.
