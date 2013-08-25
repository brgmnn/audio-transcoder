#!/bin/sh
# requries that the package vorbis-tools be installed
oggenc -q 5 "$1" -o "$2"
