#!/bin/sh
# requries that the package vorbis-tools be installed
oggenc -q 8 "$1" -o "$2"
