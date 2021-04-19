# Mr. OTCS
A script to play a list of video files in a continuous loop and produce schedules based on upcoming videos in the playlist. Requires Python 3.7 or later. 

See the [wiki](https://github.com/TheOpponent/mr-otcs/wiki) for installation instructions on Raspberry Pi and Windows.

The playlist is either a Python list or a text file with filenames:
```
Video 1.mp4
Video 2.mp4

# Comments are supported too, and blank lines are ignored
Series Name/Episode 1.mp4
Series Name/Episode 2.mp4

# Videos starting with certain words can be played but not included in the schedule
Commercial 1.mp4

Video 3.mp4
A Movie.mp4
```

The generated schedule runs up to a user-defined combined length of upcoming videos and/or any number of videos. The example HTML template in this project is intentionally very simplistic, but it uses [Day.js](https://day.js.org) for automatic timezone conversion. The script writes an array of JavaScript objects that contain video names and timestamps for their scheduled start times.

## Example schedule
![Schedule example](https://user-images.githubusercontent.com/8432212/115261634-c6f64680-a101-11eb-89aa-0c382597583f.png)

