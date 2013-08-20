#!/usr/bin/env python

import multiprocessing as mp, os, shutil, subprocess, sys, time, argparse, cPickle as pickle
import fnmatch, re
from sets import Set

class Library:
	libs = dict()
	# encoder_path = "encoders/ogg-q5.sh"
	script_path = "encoders/skip.sh"

	def __init__(self, name, source, target):
		self.name = name
		self.source = os.path.abspath(source)
		self.target = os.path.abspath(target)
		self.paths = []

		if name not in Library.libs:
			Library.libs[name] = self
		else:
			sys.stderr.write("Could not add new library as another library of the same name already exists!")

	def __str__(self):
		return self.name+" ["+str(len(self.paths))+" paths]\n" \
			+"  source dir  = "+self.source+"\n" \
			+"  target dir  = "+self.target+"\n" \
			+"  script path = "+self.script_path;

	# adds a path to the library
	def add_path(self, path):
		path = os.path.abspath(self.check_path(path))

		# if os.path.commonprefix([self.source, path]) != self.source:
		if not path.startswith(self.source):
			print "paths dont match"
			print self.source
			print path
			return 1


		# prefix = os.path.commonprefix([libs[name].source, path])
		relpath = os.path.relpath(path, self.source)
		print relpath
		print os.path.join(self.source, relpath)

		libs[name].paths.append(relpath)
		libs[name].paths.sort()
		return 0

	# remove a path from the library
	def remove_path(self, path):
		path = os.path.abspath(path)

		if not path.startswith(self.source):
			return 1

		relpath = os.path.relpath(path, self.source)

		self.paths = [p for p in self.paths if p != relpath]
		return 0

	# removes all paths under a given root directory
	def remove_path_prefix(self, prefix):
		prefix = os.path.abspath(prefix)

		if not prefix.startswith(self.source):
			return 1

		relprefix = os.path.relpath(prefix, self.source)

		self.paths = [p for p in self.paths if not p.startswith(relprefix)]
		return 0

	# list the paths associated with this library
	def list_paths(self):
		for path in self.paths:
			print "  ",path

		print "["+str(len(self.paths))+" total]"

	# print the paths in a format that can be read in again using --import-paths
	def export_paths(self):
		for path in self.paths:
			print "~~/"+path

	# checks a directory and optionally places in the libraries source dir
	def check_path(self, path):
		if path.startswith("~~/"):
			return os.path.join(self.source, path[3:])
		else:
			return path

	# applies a new transcoder
	def set_script(self, path):
		self.script_path = path

	# transcode everything that needs to be in the library
	def transcode(self):
		fext = ".flac"
		cext = [".jpg", ".png"]

		seen = set()

		for path in self.paths:
			src = os.path.join(self.source, path)

			if os.path.isfile(src) and src not in seen:
				dst = os.path.join(self.target, path)
				# print src
				# print dst
				self.transcode_worker(src, dst)
				seen.add(src)
			else:
				for root, dirs, files in os.walk(src):
					sf = [os.path.join(root, f) for f in files]
					sf = fnmatch.filter(sf, "*"+fext)

					for s in sf:
						if s not in seen:
							d = os.path.join(self.target, os.path.relpath(s, self.source))
							# print s
							# print d
							self.transcode_worker(s, d)
							seen.add(s)


	# worker thread to transcode a single item
	def transcode_worker(self, src, dst):
		if not os.path.isdir(os.path.dirname(dst)):
			os.makedirs(os.path.dirname(dst))

		devnull = open('/dev/null', 'w')
		p = subprocess.Popen([self.script_path,src,dst], stdout=devnull, stderr=devnull)
		p.wait()
		print "job done: "+dst

	# open a libraries file
	@staticmethod
	def open_libraries():
		try:
			Library.libs = pickle.load(open("libraries.p", "rb"))
		except IOError:
			print "Failed to open libraries file. Attempting to create a new file..."
			Library.save_libraries()
		return Library.libs

	# saves libraries to disk
	@staticmethod
	def save_libraries():
		try:
			pickle.dump(Library.libs, open("libraries.p", "wb"))
		except IOError:
			print "Failed to save libraries!"


def transcode(src, dst, quality):
	devnull = open('/dev/null', 'w')
	p = subprocess.Popen(["oggenc","-q",str(quality),src,"-o",dst], stdout=devnull, stderr=devnull)
	p.wait()
	print "job done: "+dst

class AudioTranscoder:
	# process a directorys
	def process_directory(self, pindex):
		print "\n~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~"
		print "    File list="+self.base_dir[pindex]+".paths"
		print "    Encoding FLACs..."
		
		self.workers = mp.Pool()
		f = open( sys.path[0]+"/"+self.base_dir[pindex]+".paths", "r" )
				

		for path in f.readlines():
			target = self.target+"/"+self.target_dir[pindex]+"/"+path.rstrip("\n")
			path = self.base+"/"+self.base_dir[pindex]+"/"+path.rstrip("\n")
			#print path
			#print target
			
			if os.path.isfile( path ) and path[len(path)-5:] == ".flac":
				name = os.path.basename(path)
				folder = path.rstrip(name)
				tardir = os.path.join(self.target, self.target_dir[pindex], folder.lstrip(os.path.join(self.base, self.base_dir[pindex])))
				
				#print name				

				oput = os.path.join(tardir,name[:len(name)-5]+".ogg")
				
				# make the target directory if we need too
				if not os.path.isdir( tardir ):
					os.makedirs( tardir )
				
				if os.path.isfile( os.path.join(folder,"cover.jpg") ):
					if not os.path.isfile( os.path.join(tardir,"cover.jpg") ):
						shutil.copy2( os.path.join(folder,"cover.jpg"), os.path.join(tardir,"cover.jpg") )
					self.target_file_set[0].add(os.path.join(tardir,"cover.jpg"))
				elif os.path.isfile( os.path.join(folder,"cover.png") ):
					if not os.path.isfile( os.path.join(tardir,"cover.png") ):
						shutil.copy2( os.path.join(folder,"cover.png"), os.path.join(tardir,"cover.png") )
					self.target_file_set[0].add(os.path.join(tardir,"cover.jpg"))
				
				if not os.path.isfile( oput ):
					self.workers.apply_async( transcode, (path, oput, self.ogg_quality) )
					#transcode( iput, oput, self.ogg_quality )
				
				self.target_file_set[0].add(oput)
				
			else:
				for root, dirs, files in os.walk( path ):
					for name in files:
						if name[len(name)-5:] == ".flac":
							tardir = os.path.join(self.target, self.target_dir[pindex], root.lstrip(os.path.join(self.base, self.base_dir[pindex])))
							
							iput = os.path.join(root,name)
							oput = os.path.join(tardir,name[:len(name)-5]+".ogg")
							
							if not os.path.isdir( tardir ):
								os.makedirs( tardir )
							
							if not os.path.isfile( oput ):
								self.workers.apply_async( transcode, (iput, oput, self.ogg_quality) )
								#transcode( iput, oput, self.ogg_quality )
							
							self.target_file_set[0].add(oput)
							
						elif name[:5] == "cover":
							#print "in:  " +root+"/"+name
							
							tardir = os.path.join(self.target, self.target_dir[pindex], root.lstrip(os.path.join(self.base, self.base_dir[pindex])))
							
							if not os.path.isdir( tardir ):
								os.makedirs( tardir )
							
							if not os.path.isfile( os.path.join(tardir,name) ):
								shutil.copy2( os.path.join(root,name), os.path.join(tardir,name) )
							
							self.target_file_set[0].add(os.path.join(tardir,name))
		
		self.workers.close()
		self.workers.join()
		
		self.clean_tree( pindex )

	# cleans a directory tree
	def clean_tree(self, pindex):
		print "\n"
		print "    Cleaning unwanted files..."
		for root, dirs, files in os.walk(os.path.join(self.target,self.target_dir[pindex]), topdown=False):
			for name in files:
				if os.path.join(root,name) not in self.target_file_set[0]:
					ext = os.path.splitext(name)[1]

					if ext != ".png" and ext != ".jpg" and ext != ".jpeg":
						os.remove(os.path.join(root, name))
						print "deleted: "+os.path.join(root, name)

			for name in dirs:
				if not os.listdir(os.path.join(root, name)):
					print "deleted: "+os.path.join(root, name)
					os.rmdir(os.path.join(root, name))

	def __init__(self):
		self.base = "/home/daniel/Music/library/"
		self.target = "/home/daniel/Music/transcode/"
		
		self.ogg_quality = 5
		
		self.base_dir = []
		self.base_dir.append("artists.flac")
		self.base_dir.append("compilations.flac")
		
		self.target_dir = []
		self.target_dir.append("artists.ogg-q5")
		self.target_dir.append("compilations.ogg-q5")
		
		self.target_file_set = []
		self.target_file_set.append(Set([]))
		self.target_file_set.append(Set([]))


#	Main
# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
if __name__ == "__main__":
	ap = argparse.ArgumentParser(description="Batch transcoding of audio files")
	
	ap.add_argument("--add-library", "-al",
		nargs=3,
		type=str,
		dest="add_library",
		metavar=("NAME", "SOURCE", "DESTINATION"),
		help="Add a library directory to the libraries list.")
	ap.add_argument("--remove-library", "-rl",
		type=str,
		dest="remove_library",
		metavar="NAME",
		help="Removes a library given the library name. This will delete the library and its associated paths.")
	ap.add_argument("--list-libraries", "-ll",
		action="store_true",
		help="Lists the library directories that are scanned for audio files.")
	ap.add_argument("--set-script-path", "-ssp",
		nargs=2,
		type=str,
		dest="set_script",
		metavar=("LIBRARY", "PATH"),
		help="Set the transcoding script path for a library.")

	ap.add_argument("--add-path", "-ap",
		nargs=2,
		type=str,
		dest="add_path",
		metavar=("LIBRARY", "PATH"),
		help="Adds a path to a library. Fails if the path given is not inside the libraries target path.")
	ap.add_argument("--import-paths", "-ip",
		type=str,
		dest="import_paths",
		metavar="LIBRARY",
		help="Imports multiple paths to the specified library. Paths are read from the standard input stream with one path per line.")
	ap.add_argument("--export-paths", "-ep",
		type=str,
		dest="export_paths",
		metavar="LIBRARY",
		help="Exports the paths for the given library to a plaintext format which can then be read in again using --import-paths.")
	ap.add_argument("--remove-path", "-rp",
		nargs=2,
		type=str,
		dest="remove_path",
		metavar=("LIBRARY", "PATH"),
		help="Remove a path from a library. Does not remove sub-paths under this path. Fails if the path does not exist in the library or if the library does not exist.")
	ap.add_argument("--remove-path-prefix", "-rpp",
		nargs=2,
		type=str,
		dest="remove_path_prefix",
		metavar=("LIBRARY", "PATH-PREFIX"),
		help="Removes all paths under PATH-PREFIX from a library.")
	ap.add_argument("--list-paths", "-lp",
		type=str,
		dest="list_paths",
		metavar="LIBRARY",
		help="Lists the paths being watched under a specified library.")

	args = ap.parse_args()
	libs = Library.open_libraries()

	# add a library
	if args.add_library:
		Library(args.add_library[0], args.add_library[1], args.add_library[2])
		Library.save_libraries()

	# remove a library
	elif args.remove_library:
		name = args.remove_library

		if name in libs:
			del libs[name]
			Library.save_libraries()

	# list the available libraries
	elif args.list_libraries:
		print "Libraries\n"
		for name, library in sorted(libs.iteritems()):
			print library

	# change a libraries transcoder using the prebuilt transcoder settings
	elif args.set_script:
		name, path = args.set_script

		if name not in libs:
			sys.exit()

		libs[name].set_script(path)
		Library.save_libraries()

	# add a path to a library
	elif args.add_path:
		name, path = args.add_path
		
		if name not in libs:
			sys.exit()

		libs[name].add_path(path)
		Library.save_libraries()

	# import multiple paths from stdin
	elif args.import_paths:
		name = args.import_paths

		if name not in libs:
			sys.exit()

		for path in sys.stdin:
			libs[name].add_path(path[:-1])

		Library.save_libraries()

	# export paths from a library
	elif args.export_paths:
		name = args.export_paths

		if name not in libs:
			sys.exit()

		libs[name].export_paths()

	# remove a path from a library
	elif args.remove_path:
		name, path = args.remove_path

		if name not in libs:
			sys.exit()

		libs[name].remove_path(path)
		Library.save_libraries()

	# remove paths from a library
	elif args.remove_path_prefix:
		name, prefix = args.remove_path_prefix

		if name not in libs:
			sys.exit()

		libs[name].remove_path_prefix(prefix)
		Library.save_libraries()

	# list paths for a library
	elif args.list_paths:
		if args.list_paths in libs:
			libs[args.list_paths].list_paths()
		else:
			print "Could not find library",args.list_paths

	# transcode anything that's missing
	else:
		at = AudioTranscoder()
		
		print "--- Audio Transcoder ---"
		print "  Workers: "+str(mp.cpu_count())

		for name, library in sorted(libs.iteritems()):
			library.transcode()

		# at.process_directory(0)
		# at.process_directory(1)
