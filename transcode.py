#!/usr/bin/env python

import multiprocessing as mp, os, shutil, subprocess, sys, time, argparse, cPickle as pickle
from sets import Set

class Library:
	libs = dict()

	def __init__(self, name, source, target):
		self.name = name
		self.source = source
		self.target = target

		if name not in Library.libs:
			Library.libs[name] = self
		else:
			sys.stderr.write("Could not add new library as another library of the same name already exists!")

	def __str__(self):
		return self.name+": '"+self.source+"' -> '"+self.target+"'"

	# open a libraries file
	@staticmethod
	def open_libraries():
		try:
			Library.libs = pickle.load(open("libraries.p", "rb"))
		except IOError:
			print "Failed to open libraries file. Attempting to create a new file..."
			Library.save_libraries()
		return Library.libs

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
	
	ap.add_argument("--list-libraries", "-ll",
		action="store_true",
		help="Lists the library directories that are scanned for audio files.")
	ap.add_argument("--add-library", "-al",
		nargs=3,
		type=str,
		dest="add_library",
		metavar=("NAME", "SOURCE", "DESTINATION"),
		help="Add a library directory to the libraries list.")
	ap.add_argument("--remove-library", "-rl",
		nargs=1,
		type=str,
		dest="remove_library",
		metavar="NAME",
		help="Removes a library given the library name. This will delete the library and its associated paths.")

	ap.add_argument("--add-path",
		nargs=2,
		type=str,
		dest="add_path",
		metavar=("LIBRARY", "PATH"),
		help="Adds the path PATH to the library named LIBRARY. Fails if the path given is not inside the libraries target path.")

	args = ap.parse_args()

	# list the available libraries
	if args.list_libraries:
		print "Libraries:"
		libs = Library.open_libraries()
		for name, library in libs.iteritems():
			print "  ",library

	# add a library
	elif args.add_library:
		Library.open_libraries()
		Library(args.add_library[0], args.add_library[1], args.add_library[2])
		Library.save_libraries()

	# remove library
	elif args.remove_library:
		Library.open_libraries()

	# add a path to a library
	elif args.add_path:
		libs = Library.open_libraries()
		prefix = os.path.commonprefix(["/home/daniel", "/home"])
		print prefix

	# transcode anything that's missing
	else:
		at = AudioTranscoder()
		
		print "--- Audio Transcoder ---"
		
		print "    Workers: "+str(mp.cpu_count())
		print "  Base path: "+at.base
		print "Target base: "+at.target
		
		at.process_directory(0)
		at.process_directory(1)
