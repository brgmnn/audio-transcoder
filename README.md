# Audio Transcoder #

Batch transcode audio files. Some features:

* Multithreaded. Transcode large numbers of files faster.
* Libraries. Organise and transcode only a subset of files under a directory, selecting individual files or whole folders.
* Differential. Only transcode the files you have to, don't transcode files that have previously.
* Copy Files. Copy album art or any other file with your transcoded files selected by file extension.

## Installation ##

Clone this git repo to your computer.
You can do this by executing the following git command in the folder where you want the repo to be cloned:

	git clone https://github.com/brgmnn/audio-transcoder.git

#### Optional step 2 ####

Then if you want to install the transcoder to your /usr/local/bin folder, execute the install script from the repo folder:

	sudo ./install.sh

This just creates a symbolic link to `atran.py`.
You can now call the transcoder from any folder with `atran`.

#### Requirements ####

* Python 2.7.
* Sqlite
* Some kind of audio conversion tool. For the encoder scripts provided you
    need `lame` for MP3 and `oggenc` for OGG Vorbis.

I develop/test primarily on Ubuntu/Linux Mint.
Atran is _not_ tested on Windows however it does run in Cygwin.

#### Uninstallation ####

Delete the repo folder you have cloned and delete the link in /usr/local/bin if you ran install.sh.

## Quick start, or "I just want to transcode my files!" ##

First prepare your [script file](http://github.com/brgmnn/audio-transcoder/wiki/scripts), or just modify the default one provided.
Your script file will be called on each file to be transcoded individually and will be called with `./your-script.sh [source_file] [output_file]`.
Here is the contents of the default script file:

	#!/bin/sh
	lame -V 0 "$1" "$2"

Very simple, `$1` is the source file path and `$2` is the output file path.
This script encodes `$1` using the lame mp3 encoder with variable bitrate quality 0 and places the output in `$2`.
You will need lame installed to use this default script.
If you are not sure about how your script file should look like, there are several example scripts provided in the `encoders` folder.

Next modify [settings.json](http://github.com/brgmnn/audio-transcoder/wiki/settings.json) to set the source file extension and output file extension as well as the location of your script file.
If you want to transcode _.wav_ files to _.mp3_ files then edit settings.json to look like:

	{
		"default_exts": [".wav", ".mp3"]
		"default_script_path": "/path/to/my/script.sh"
	}

The source file extension is the first item in the list and the output file extension is the second for the `default_exts` key.
Note that if you just modified the default script which comes with the transcoder (default-script.sh) then you don't need to set the `default_script_path` key.

Finally run the Audio Transcoder with:

	atran run *source_folder* *output_folder*

That's it! As the transcoder runs it will print out the files it has finished.

The transcoder will scan through the source folder and will transcode all files that it finds with the source file extension.
The output files will be placed in the same relative paths as they are under the source folder with the same name but with the output file extension.

More information on [settings.json](http://github.com/brgmnn/audio-transcoder/wiki/settings.json)

## Library Model ##

The library model is aimed at managing a subset of files where only the subset is to be transcoded.
The audio transcoder can have an arbitrary number of libraries.
Each library has a root source directory and a root target directory as well as a list of tracked paths.
All paths associated with a library are located under the source directory.
Only the list of tracked paths will be transcoded from the source directory.
Other files will be ignored.
Transcoded files will be placed in the target directory in the same relative path as their source counterpart.
As well as transcoding files, the library can also copy files (selected by file extension) to the target directory (think album art that you want copied over).

## Example ##

### Library basics ###

I have a music library of WAV files.
However I want to listen to some of these files on my smartphone.
I want a subset consisting of my favourite tunes to be transcoded to MP3 to conserve space on my moderately small SD card.
I begin by executing (if you see a warning about missing a database file, don't worry a new database file will be automatically created):

    atran library --new music ~/Music /media/smartphone/Music

This creates a new library called "music" with a root source directory `~/Music` and a root target directory `/media/smartphone/Music`.
I don't want all of my audio files transcoded so I add some paths to my library "music".
Paths not under the root source directory `~/Music` will fail.
The shorthand `~~/` can be used to specify a path relative to the libraries root source directory.
Paths can be either directories or files (files given should be valid files to be transcoded).
In the case of a directory, _all_ valid files underneath that directory will be transcoded.
I add some folders and files:

    atran path --add music ~/Music/Muse/Showbiz/
    atran path --add music ~/Music/Muse/Absolution
    atran path --add music ~~/Bach
    atran path --add music "~~/Flo Rida/Low.wav"

Next I decide that I also want my album art to be copied over to my phone as well.
I want all _.jpg_ files under any paths to be copied so I add the _.jpg_ extension to the "music" library *copy extension list*, which is just a list of all the file extensions to be copied over.

	atran library --add-copy-ext music .jpg

Great! Now I want to transcode the files so I run:

	atran run

Calling `atran.py run` with no arguments will process all the libraries in it's database. Alternatively to explicitly only process the "music" library run:

	atran run music

That's it! A list of all the files being transcoded will appear as they are completed.

## More Examples and the wiki ##

There are more examples and a list of all the functions available with the transcoder in the wiki.

