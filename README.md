# Audio Transcoder #

Batch transcode audio files organised in libraries

## Quick start, or "I just want to transcode my files!" ##

First prepare your script file, or just modify the default one provided.
Your script file will be called on each item to be transcoded and will be called with `./your-script.sh *source_file* *output_file*`.
Here is the contents of the default script file:

	#!/bin/sh
	oggenc -q 5 "$1" -o "$2"

Very simple, with `$1` containing the source file and `$2` containing the output file.
This script encodes `$1` using the vorbis encoder at q=5 and places the output in `$2`.
You will need vorbis-tools installed to use this default script.

## Examples ##

Examples usage

### Libraries Explained ###

Collections of files are organised in to libraries.
Each library has a root source directory and a root target directory.
All files to be transcoded should be located under the root source directory.
After transcoding the output files will be placed in the root target directory under the same relative path as their corresponding source files.
However not all files under the root source directory must necessarily be transcoded.
Each library has a list of paths which are files or whole folders under the root source directory which are to be transcoded.
Only the paths in the paths list are transcoded.
As well as transcoding files, the library will copy files (with specified file extensions) to the root target directory (think album art that you want copied over).

You can have as many libraries as you want, with no restriction on how they overlap with source roots or paths. It is advisable to set each libraries target root to be a unique directory.

#### Example ####

I have a collection of FLAC audio files representing my music collection on my desktop. However I want to listen to some of these files on my smartphone. I want a subset of my music library to be transcoded to OGG vorbis to conserve space on my moderate SD card. I begin by executing:

    ./transcode.py --add-library music ~/Music ~/PhoneMusic

This creates a new library called "music" with a root source directory `~/Music` and a root target directory `~/PhoneMusic`. I don't want all of my audio files transcoded so I add some paths to my "music" library. Paths not under the root source directory `~/Music` will fail. The shorthand `~~/` can be used to specify a path relative to the libraries root source directory. Paths can be either directories or files. In the case of a directory, _all_ valid files underneath that directory will be transcoded. I add some paths:

    ./atran.py path --add music ~/Music/Muse/Showbiz/
    ./atran.py path --add music ~/Music/Muse/Absolution
    ./atran.py path --add music ~~/Bach
    ./atran.py path --add music ~~/
