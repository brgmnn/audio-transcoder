#!/usr/bin/env python

import multiprocessing as mp, os, shutil, subprocess, sys, time, argparse, pickle, StringIO
import fnmatch, re, json, sqlite3
from sets import Set

db_connection = sqlite3.connect("profile.db3")

# space separate variable list
def ssv_list(lst):
	output = StringIO.StringIO()
	for item in lst:
		output.write(item)
		output.write(" ")
	return output.getvalue().strip()

#*		Settings
#*	holds the global settings for the transcoder.
#*~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~*#
class Settings:
	properties = dict()

	@staticmethod
	def open():
		try:
			defaults = json.load(open("default-settings.json", "rb"))
			values = json.load(open("settings.json", "rb"))
			Settings.properties = dict(defaults.items() + values.items())
		except IOError:
			print "Failed to open one of the settings files. Attempting to create it now..."
			Settings.save()
		return Settings.properties

	@staticmethod
	def save():
		try:
			Settings.properties["default_copy_exts"].sort()
			open("composite.json", "wb").write(\
				json.dumps(Settings.properties, sort_keys=True, indent=4,\
					separators=(',', ': ')))
		except IOError:
			print "Failed to save settings."

#*		Library
#*	handles each library of audio files.
#*~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~*#
class Library:
	def __init__(self, *args, **kwargs):
		if len(args) == 1:
			c = db_connection.cursor()
			c.execute("SELECT * FROM libraries WHERE name=?", (args[0],))
			row = c.fetchone()

			self.id = row[0]
			self.name = row[1]
			self.source = row[2]
			self.target = row[3]
			self.script_path = row[4]
			self.exts = [row[5], row[6]]
			self.cexts = row[7].split(" ")
			self.paths = []
		else:
			self.name = args[0]
			self.source = os.path.abspath(args[1])
			self.target = os.path.abspath(args[2])
			self.paths = []
			self.script_path = Settings.properties["default_script_path"].encode('ascii', 'ignore')
			self.exts = [e for e in Settings.properties["default_exts"]]
			self.cexts = [e for e in Settings.properties["default_copy_exts"]]
			
			c = db_connection.cursor()
			c.execute("INSERT INTO libraries VALUES (NULL,?,?,?,?,?,?,?)",
				(	self.name,
					self.source,
					self.target,
					self.script_path,
					self.exts[0],
					self.exts[1],
					ssv_list(self.cexts) )
				)
			db_connection.commit()

	def __str__(self):
		return self.name+" ["+str(len(self.paths))+" paths]\n" \
			+"  source dir  = "+self.source+"\n" \
			+"  target dir  = "+self.target+"\n" \
			+"  script path = "+self.script_path+"\n" \
			+"  source ext  = "+self.exts[0]+"\n" \
			+"  target ext  = "+self.exts[1]+"\n" \
			+"  copy exts   = "+str(self.cexts);

	# adds a path to the library
	def add_path(self, path):
		path = os.path.abspath(self.check_path(path))

		if not path.startswith(self.source):
			print "paths dont match"
			print self.source
			print path
			return 1

		c = db_connection.cursor()
		c.execute("INSERT INTO paths VALUES (NULL,?,?)", \
			(self.id, os.path.relpath(path, self.source)))
		db_connection.commit()
		return 0

	# remove a path from the library
	def remove_path(self, path):
		path = os.path.abspath(self.check_path(path))

		if not path.startswith(self.source):
			print "Path not under root!"
			return 1

		c = db_connection.cursor()
		c.execute("DELETE FROM paths WHERE lid=? AND path=?", \
			(self.id, os.path.relpath(path, self.source)))
		db_connection.commit()
		return 0

	# removes all paths under a given root directory
	def remove_path_prefix(self, prefix):
		prefix = os.path.abspath(self.check_path(prefix))

		if not prefix.startswith(self.source):
			print "Path not under root!"
			return 1

		c = db_connection.cursor()
		c.execute("DELETE FROM paths WHERE lid=? AND path LIKE ?", \
			(self.id, os.path.relpath(prefix, self.source)+"%") )
		db_connection.commit()
		return 0

	# sets the script path
	def set_script_path(self, path):
		c = db_connection.cursor()
		c.execute("UPDATE libraries SET script_path=? WHERE id=?", (path, self.id))
		db_connection.commit()

	# manipulate the extensions
	def ext(self, *args, **kwargs):
		c = db_connection.cursor()
		if args[0] == "source":
			c.execute("UPDATE libraries SET source_ext=? WHERE id=?", (args[1], self.id))
		elif args[0] == "target":
			c.execute("UPDATE libraries SET target_ext=? WHERE id=?", (args[1], self.id))
		elif args[0] == "copy":
			if "append" in kwargs:
				new_cexts = list(self.cexts)
				new_cexts.extend(kwargs["append"].split())
				new_cexts = list(set(new_cexts))
				new_cexts.sort()
				c.execute("UPDATE libraries SET copy_ext=? WHERE id=?", \
					(ssv_list(new_cexts), self.id))
			elif "set" in kwargs:
				c.execute("UPDATE libraries SET copy_ext=? WHERE id=?", \
					(ssv_list(kwargs["set"]), self.id))
		else:
			return
		db_connection.commit()

	# queries the database and returns all the paths associated with it
	def fetch_paths(self):
		c = db_connection.cursor()
		c.execute("SELECT path FROM paths WHERE lid=? ORDER BY path ASC", (self.id,))
		self.paths = [p[0] for p in c.fetchall()]
		return self.paths

	# list the paths associated with this library
	def list_paths(self):
		for path in self.fetch_paths():
			print "  ",path
		print "["+str(len(self.paths))+" total]"

	# print the paths in a format that can be read in again using --import-paths
	def export_paths(self):
		for path in self.fetch_paths():
			print "~~/"+path

	# checks a directory and optionally places in the libraries source dir
	def check_path(self, path):
		if path.startswith("~~/"):
			return os.path.join(self.source, path[3:])
		return path

	# transcode everything that needs to be in the library
	def transcode(self, workers):
		seen = set()

		self.items = 0;
		self.current = 0;

		for path in self.fetch_paths():
			src = os.path.join(self.source, path)

			if os.path.isfile(src) and src not in seen:
				dst = os.path.join(self.target, path)

				if src[-len(self.exts[0]):] == self.exts[0]:
					dst = dst[:-len(self.exts[0])]+self.exts[1]
					if not os.path.isdir(os.path.dirname(dst)):
						os.makedirs(os.path.dirname(dst))
					
					if Settings.properties["multithreaded"]:
						workers.apply_async(transcode_worker, (self.script_path, src, dst))
					else:
						transcode_worker(self.script_path, src, dst)
				else:
					if not os.path.isdir(os.path.dirname(dst)):
						os.makedirs(os.path.dirname(dst))
					shutil.copy2(src,dst)

				seen.add(src)
			else:
				for root, dirs, files in os.walk(src):
					files = [os.path.join(root, f) for f in files]
					sf = fnmatch.filter(files, "*"+self.exts[0])

					for c in self.cexts:
						sf.extend(fnmatch.filter(files, "*"+c))

					for s in sf:
						if s not in seen:
							d = os.path.join(self.target, os.path.relpath(s, self.source))

							if s[-len(self.exts[0]):] == self.exts[0]:
								d = d[:-len(self.exts[0])]+self.exts[1]
								
								if not os.path.isdir(os.path.dirname(d)):
									os.makedirs(os.path.dirname(d))
								
								if Settings.properties["multithreaded"]:
									workers.apply_async(transcode_worker, (self.script_path, s, d))
								else:
									transcode_worker(self.script_path, s, d)
							else:
								if not os.path.isdir(os.path.dirname(d)):
									os.makedirs(os.path.dirname(d))
								shutil.copy2(s,d)

							seen.add(s)

	# cleans the tree of unwanted files
	def clean_tree(self):
		for root, dirs, files in os.walk(self.target):
			dirs = [os.path.join(root, d) for d in dirs]
			files = [os.path.join(root, f) for f in files]
			valid = fnmatch.filter(files, "*"+self.exts[1])

			for c in self.cexts:
				valid.extend(fnmatch.filter(files, "*"+c))

			rm_files = list(set(files) - set(valid))
			for path in rm_files:
				os.remove(path)

			for d in dirs:
				try:
					os.rmdir(d)
				except OSError as ex:
					pass

	def write_progress(self):
		sys.stdout.write("\rdone "+str(self.current)+" / "+str(self.items))
		sys.stdout.flush()

	# encodes the library to a json string
	def json_encode(self):
		d = dict()
		d["name"] = self.name
		d["source"] = self.source
		d["target"] = self.target
		d["paths"] = self.paths
		d["script_path"] = self.script_path
		d["exts"] = self.exts
		d["cexts"] = self.cexts
		return json.dumps(d, sort_keys=True, indent=4, separators=(',', ': '))

	# decodes and updates this library from a json string
	def json_decode(self, json_string):
		d = json.loads(json_string)
		self.name = d["name"]
		self.source = d["source"]
		self.target = d["target"]
		self.paths = d["paths"]
		self.script_path = d["script_path"]
		self.exts = d["exts"]
		self.cexts = d["cexts"]

	# lists the names of all the libraries
	@staticmethod
	def list_names():
		c = db_connection.cursor()
		c.execute("SELECT name FROM libraries ORDER BY name ASC")
		return [n[0] for n in c.fetchall()]

	# removes a library given its name
	@staticmethod
	def remove(name):
		c = db_connection.cursor()
		c.execute("SELECT id FROM libraries WHERE name=?", (name,))
		lid = c.fetchone()[0]

		c.execute("DELETE FROM libraries WHERE name=?", (name,))
		c.execute("DELETE FROM paths WHERE lid=?", (lid,))
		db_connection.commit()

# worker thread to transcode a single item
def transcode_worker(script_path, src, dst):
	devnull = open('/dev/null', 'w')
	p = subprocess.Popen([script_path,src,dst], stdout=devnull, stderr=devnull)
	p.wait()
	print "job done: "+dst

#	Main
# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
if __name__ == "__main__":
	ap = argparse.ArgumentParser(description="Batch transcoding of audio files")
	
	# library operations
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
	ap.add_argument("--set-source-extension", "-sse",
		nargs=2,
		type=str,
		dest="set_source_ext",
		metavar=("LIBRARY", "EXTENSION"),
		help="Set the source file extension. This should include the preceeding period. Example: for FLAC source audio files, set this extension to '.flac'")
	ap.add_argument("--set-target-extension", "-ste",
		nargs=2,
		type=str,
		dest="set_target_ext",
		metavar=("LIBRARY", "EXTENSION"),
		help="Set the target output file extension. This should include the preceeding period. Example: for MP3 output files, set this extension to '.mp3'")
	ap.add_argument("--add-copy-extension", "-ace",
		nargs=2,
		type=str,
		dest="add_copy_ext",
		metavar=("LIBRARY", "EXTENSION(S)"),
		help="Add copy extensions. Multiple extensions can be specified, separated by a comma. Copy extensions are a list of file extensions which files are to be copied over from the source to target tree. This could be used to copy image files so that album art is transfered over to the target directory.")
	ap.add_argument("--clear-copy-extensions", "-cce",
		type=str,
		dest="clear_copy_exts",
		metavar="LIBRARY",
		help="Clears the copy extension list for a library. After calling this command no files will be copied over from the source to target tree.")

	# path operations
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

	# profile operations
	ap.add_argument("--create-profile", "-cp",
		action="store_true",
		dest="create_profile",
		help="Creates a new blank profile. A profile contains all libraries, paths and settings for the application.")

	args = ap.parse_args()
	settings = Settings.open()

	# add a library
	if args.add_library:
		Library(args.add_library[0], args.add_library[1], args.add_library[2])

	# remove a library
	elif args.remove_library:
		name = args.remove_library
		Library.remove(name)

	# list the available libraries -SQL
	elif args.list_libraries:
		print "Libraries\n"
		for name in Library.list_names():
			print Library(name)

	# change a libraries transcoder using the prebuilt transcoder settings
	elif args.set_script:
		name, path = args.set_script
		Library(name).set_script_path(path)

	# set the source file extensions
	elif args.set_source_ext:
		name, ext = args.set_source_ext
		Library(name).ext("source",ext)

	# set the target file extensions
	elif args.set_target_ext:
		name, ext = args.set_target_ext
		Library(name).ext("target",ext)

	# adds extensions to the copy list
	elif args.add_copy_ext:
		name, exts = args.add_copy_ext
		Library(name).ext("copy",append=exts.replace(",", " "))

	# clears the copy list for the library
	elif args.clear_copy_exts:
		name = args.clear_copy_exts
		Library(name).ext("copy",set="")

	# creates a new database profile. will delete the contents of an existing "profile.db3"!
	elif args.create_profile:
		db_connection.close()
		fp = open("profile.db3", "rw+")
		fp.truncate()
		fp.close()
		
		db_connection = sqlite3.connect("profile.db3")
		c = db_connection.cursor()
		c.execute("CREATE TABLE libraries \
			(	id INTEGER PRIMARY KEY, \
				name TEXT, \
				source TEXT, \
				target TEXT, \
				script_path TEXT, \
				source_ext TEXT, \
				target_ext TEXT, \
				copy_ext TEXT, \
				UNIQUE (name))")

		c.execute("CREATE TABLE paths \
			(	id INTEGER PRIMARY KEY, \
				lid INTEGER, \
				path TEXT, \
				UNIQUE (lid, path) \
				FOREIGN KEY (lid) REFERENCES libraries(id))")

		db_connection.commit()

	# add a path to a library
	elif args.add_path:
		name, path = args.add_path
		Library(name).add_path(path)

	# import multiple paths from stdin
	elif args.import_paths:
		name = args.import_paths

		lib = Library(name)
		for path in sys.stdin:
			lib.add_path(path[:-1])

	# export paths from a library
	elif args.export_paths:
		name = args.export_paths
		Library(name).export_paths()

	# remove a path from a library
	elif args.remove_path:
		name, path = args.remove_path
		Library(name).remove_path(path)

	# remove paths from a library
	elif args.remove_path_prefix:
		name, prefix = args.remove_path_prefix
		Library(name).remove_path_prefix(prefix)

	# list paths for a library
	elif args.list_paths:
		Library(args.list_paths).list_paths()

	# transcode anything that's missing
	else:
		print "--- Audio Transcoder ---"
		print "  Workers: "+str(mp.cpu_count())

		workers = []
		if Settings.properties["multithreaded"]:
			if Settings.properties["cores"] > 1:
				workers = mp.Pool(Settings.properties["cores"])
			else:
				workers = mp.Pool()

		for name in sorted(Library.list_names()):
			lib = Library(name)
			lib.clean_tree()
			lib.transcode(workers)

		if Settings.properties["multithreaded"]:
			workers.close()
			workers.join()

	db_connection.close()
