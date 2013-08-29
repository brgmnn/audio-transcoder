#!/bin/sh
# requries that the package vorbis-tools be installed
oggenc -q 9 "$1" -o "$2"
