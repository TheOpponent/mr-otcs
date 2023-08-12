# Mr. OTCS
A script to play a list of video files in a continuous loop, transcode it to RTMP, and produce schedules based on upcoming videos in the playlist. Requires Python 3.7 or later. 

## Features
- Stream any number of video files supported by ffmpeg in sequence, looping forever
- Playlist information is generated in a JSON file as every video begins, to be uploaded to a web server that shows your channel's schedule
- The stream can be restarted within a certain amount of elapsed time, to prevent an interruption in the middle of a video
- Separate bumper videos can be defined before and after the stream would be restarted, to inform viewers of the break
- Attempts to detect internet connection issues and suspends encoding until the internet connection is re-established, resuming from where it left off

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

# Command keywords to control the stream
%RESTART

Video Name 5.mp4
```

### Example schedule
![Example schedule](https://user-images.githubusercontent.com/8432212/222037873-c182c36b-5896-4822-8003-1c7f613296ba.png)

The generated schedule runs up to a user-defined combined length of upcoming videos and/or any number of videos. The script writes an array of JavaScript objects that contain video names and timestamps for their scheduled start times. A basic HTML file is provided as a quick demonstration of such JSON usage, including parsing metadata in the playlist.

## Installation
The recommended environment is a headless Raspberry Pi, but conventional Linux systems, including WSL2, can also run Mr. OTCS. See the [wiki](https://github.com/TheOpponent/mr-otcs/wiki) for installation instructions.

Mr. OTCS reads a text file and starts a video encoder (ffmpeg by default) for each valid video filename within in turn, streaming it to a local RTMP server such as nginx. Another ffmpeg process relays the transcoded video a third-party video streaming service. This is made possible with [**a fork of ffmpeg**](https://github.com/neckro/FFmpeg) by [neckro](https://github.com/neckro) with support for repairing HLS discontinuities. These two processes together create an endless, seamless stream of video content from any number of video files supported by ffmpeg. Because some services automatically terminate streams after a certain amount of time (e.g. Twitch ends streams after 48 consecutive hours), Mr. OTCS tracks the total streaming time and automatically restarts the stream between video files, so no interruption happens in the middle of a video.

# Disclaimer
Use this script at your own risk. The authors assume no responsibility for any administrative action taken on streaming accounts as a result of this script.
