# Audio Transcoder #

Batch transcode audio files organised in libraries

##  ##

### Libraries Explained ###

Collections of files are organised in to libraries. Each library has a root source directory and a root target directory. All files to be transcoded should be located under the root source directory. After transcoding the output files will be placed in the root target directory under the same relative path as their corresponding source files. However not all files under the root source directory must necessarily be transcoded. Each library has a list of paths which are files or whole folders under the root source directory which are to be transcoded. Only the paths in the paths list are transcoded. As well as transcoding files, the library will copy files (with specified file extensions) to the root target directory (think album art that you want copied over).

You can have as many libraries as you want, with no restriction on how they overlap with source roots or paths. It is advisable to set each libraries target root to be a unique directory.

#### Example ####

I have a collection of FLAC audio files representing my music collection on my desktop. However I want to listen to some of these files on my smartphone. I want a subset of my music library to be transcoded to OGG vorbis to conserve space on my moderate SD card. I begin by executing:

    ./transcode.py --add-library music ~/Music ~/PhoneMusic

This creates a new library called "music" with a root source directory `~/Music` and a root target directory `~/PhoneMusic`.
