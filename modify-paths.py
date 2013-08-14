#!/usr/bin/env python

import sys

if __name__ == "__main__":
	base = "/home/daniel/Music/"
	
	afr = open(sys.path[0]+"/artists.flac.paths", "r")
	cfr = open(sys.path[0]+"/compilations.flac.paths", "r")
	
	paths_a = afr.readlines()
	paths_c = cfr.readlines()
	
	afr.close()
	cfr.close()
	
	rm = False
	for path in sys.argv[1:]:
		print path
		if path == "-r":
			rm = True
		elif not rm:
			path = path[len(base):]
			if path[len(path)-1:] == "/":
				path = path[:-1]
			
			if path[:len("artists.flac/")] == "artists.flac/":
				print "In artists.flac.paths: "+path[len("artists.flac/"):]
				paths_a.append(path[len("artists.flac/"):]+"\n")
			
			if path[:len("compilations.flac/")] == "compilations.flac/":
				print "In compilations.flac.paths: "+path[len("compilations.flac/"):]
				paths_c.append(path[len("compilations.flac/"):]+"\n")
		else:
			path = path[len(base):]
			if path[len(path)-1:] == "/":
				path = path[:-1]
			
			if path[:len("artists.flac/")] == "artists.flac/":
				print "In artists.flac.paths: "+path[len("artists.flac/"):]
				try:
					paths_a.remove(path[len("artists.flac/"):]+"\n")
				except:
					pass
			if path[:len("compilations.flac/")] == "compilations.flac/":
				print "In compilations.flac.paths: "+path[len("compilations.flac/"):]
				try:
					paths_c.remove(path[len("compilations.flac/"):]+"\n")
				except:
					pass
			rm = False
	
	paths_a = list(set(paths_a))
	paths_c = list(set(paths_c))
	paths_a.sort()
	paths_c.sort()

	afw = open(sys.path[0]+"/artists.flac.paths", "w")
	cfw = open(sys.path[0]+"/compilations.flac.paths", "w")
	
	for p in paths_a:
		afw.write(p)
	
	for p in paths_c:
		cfw.write(p)
	
	afw.close()
	cfw.close()
