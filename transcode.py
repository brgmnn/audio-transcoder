#!/usr/bin/env python

import multiprocessing as mp, os, shutil, subprocess, sys, time, argparse, pickle, StringIO
import fnmatch, re, json, sqlite3
from sets import Set

dbc = sqlite3.connect("profile.db3")
dbc.row_factory = sqlite3.Row

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
			c = dbc.cursor()
			c.execute("SELECT * FROM libraries WHERE name=?", (args[0],))
			row = c.fetchone()

			try:
				self.id = row["id"]
				self.name = row["name"]
				self.source = row["source"]
				self.target = row["target"]
				self.script_path = row["script_path"]
				self.exts = [row["source_ext"], row["target_ext"]]
				self.cexts = row["copy_ext"].split(" ")
				self.paths = []
			except TypeError:
				print "Could not find library named '"+args[0]+"' in database."
				sys.exit(1)
		else:
			self.name = args[0]
			self.source = os.path.abspath(args[1])
			self.target = os.path.abspath(args[2])
			self.paths = []
			self.script_path = Settings.properties["default_script_path"].encode('ascii', 'ignore')
			self.exts = [e for e in Settings.properties["default_exts"]]
			self.cexts = [e for e in Settings.properties["default_copy_exts"]]
			
			c = dbc.cursor()
			c.execute("INSERT INTO libraries VALUES (NULL,?,?,?,?,?,?,?)",
				(	self.name,
					self.source,
					self.target,
					self.script_path,
					self.exts[0],
					self.exts[1],
					ssv_list(self.cexts) )
				)
			c.execute("SELECT id FROM libraries WHERE name=?", (self.name,))
			self.id = c.fetchone()["id"]
			dbc.commit()

	def __str__(self):
		val = dbc.execute("SELECT COUNT(path) FROM paths WHERE lid=?", (self.id,)).fetchone()[0]
		return self.name+" ["+str(val)+" paths]\n" \
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

		try:
			dbc.execute("INSERT INTO paths VALUES (NULL,?,?)", \
				(self.id, os.path.relpath(path, self.source)))
			dbc.commit()
		except sqlite3.IntegrityError:
			print "path already in database!"
			return 1
		return 0

	# remove a path from the library
	def remove_path(self, path):
		path = os.path.abspath(self.check_path(path))

		if not path.startswith(self.source):
			print "Path not under root!"
			return 1

		dbc.execute("DELETE FROM paths WHERE lid=? AND path=?", \
			(self.id, os.path.relpath(path, self.source)))
		dbc.commit()
		return 0

	# removes all paths under a given root directory
	def remove_path_prefix(self, prefix):
		prefix = os.path.abspath(self.check_path(prefix))

		if not prefix.startswith(self.source):
			print "Path not under root!"
			return 1

		dbc.execute("DELETE FROM paths WHERE lid=? AND path LIKE ?", \
			(self.id, os.path.relpath(prefix, self.source)+"%") )
		dbc.commit()
		return 0

	# sets the script path
	def set_script_path(self, path):
		dbc.execute("UPDATE libraries SET script_path=? WHERE id=?", (path, self.id))
		dbc.commit()

	# manipulate the extensions
	def ext(self, *args, **kwargs):
		if args[0] == "source":
			dbc.execute("UPDATE libraries SET source_ext=? WHERE id=?", (args[1], self.id))
		elif args[0] == "target":
			dbc.execute("UPDATE libraries SET target_ext=? WHERE id=?", (args[1], self.id))
		elif args[0] == "copy":
			if "append" in kwargs:
				new_cexts = list(self.cexts)
				new_cexts.extend(kwargs["append"].split())
				new_cexts = list(set(new_cexts))
				new_cexts.sort()
				dbc.execute("UPDATE libraries SET copy_ext=? WHERE id=?", \
					(ssv_list(new_cexts), self.id))
			elif "set" in kwargs:
				dbc.execute("UPDATE libraries SET copy_ext=? WHERE id=?", \
					(ssv_list(kwargs["set"]), self.id))
		else:
			return
		dbc.commit()

	# queries the database and returns all the paths associated with it
	def fetch_paths(self):
		c = dbc.cursor()
		c.execute("SELECT path FROM paths WHERE lid=? ORDER BY path ASC", (self.id,))
		self.paths = [p["path"] for p in c.fetchall()]
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
		return [n["name"] for n in dbc.execute("SELECT name FROM libraries ORDER BY name ASC")]

	# removes a library given its name
	@staticmethod
	def remove(name):
		lid = dbc.execute("SELECT id FROM libraries WHERE name=?", (name,)).fetchone()["id"]
		dbc.execute("DELETE FROM libraries WHERE name=?", (name,))
		dbc.execute("DELETE FROM paths WHERE lid=?", (lid,))
		dbc.commit()

# worker thread to transcode a single item
def transcode_worker(script_path, src, dst):
	devnull = open('/dev/null', 'w')
	p = subprocess.Popen([script_path,src,dst], stdout=devnull, stderr=devnull)
	p.wait()
	print "job done: "+dst

#	Tool Commands
# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
# edit libraries
def cmd_library(args):
	if args.new:
		# add a library
		Library(args.new[0], args.new[1], args.new[2])
	elif args.delete:
		# deletes a library
		Library.remove(args.delete)
	elif args.script:
		# set script path
		name, path = args.script
		Library(name).set_script_path(path)
	elif args.source_ext:
		# set source extension
		name, ext = args.source_ext
		Library(name).ext("source",ext)
	elif args.target_ext:
		# set target extension
		name, ext = args.target_ext
		Library(name).ext("target",ext)
	elif args.add_copy:
		# add copy extension
		name, exts = args.add_copy
		Library(name).ext("copy",append=exts.replace(",", " "))
	elif args.clear_copy:
		# remove all copy extensions
		name = args.clear_copy
		Library(name).ext("copy",set="")

# list libraries or paths of libraries
def cmd_list(args):
	if args.paths:
		# list paths of a library
		Library(args.paths).list_paths()
	else:
		# default - list the libraries
		print "Libraries\n"
		for name in Library.list_names():
			print Library(name)

# edit paths
def cmd_path(args):
	if args.add:
		# add a path to a library
		name, path = args.add
		Library(name).add_path(path)
	elif args.import_paths:
		# import multiple paths from stdin
		lib = Library(args.import_paths)
		for path in sys.stdin:
			lib.add_path(path[:-1])
	elif args.export:
		# export paths from a library
		Library(args.export).export_paths()
	elif args.remove:
		# remove a path from a library
		name, path = args.remove
		Library(name).remove_path(path)
		# remove paths from a library
	elif args.remove_tree:
		name, prefix = args.remove_tree
		Library(name).remove_path_prefix(prefix)

# at the moment just to initialise the profile database.
def cmd_profile(args):
	if args.new:
		# creates a new database profile. will delete the contents of an existing "profile.db3"!
		fp = open("profile.db3", "rw+")
		fp.truncate()
		fp.close()
		
		dbc = sqlite3.connect("profile.db3")
		dbc.execute("CREATE TABLE libraries \
			(	id INTEGER PRIMARY KEY, \
				name TEXT, \
				source TEXT, \
				target TEXT, \
				script_path TEXT, \
				source_ext TEXT, \
				target_ext TEXT, \
				copy_ext TEXT, \
				UNIQUE (name))")
		dbc.execute("CREATE TABLE paths \
			(	id INTEGER PRIMARY KEY, \
				lid INTEGER, \
				path TEXT, \
				UNIQUE (lid, path) \
				FOREIGN KEY (lid) REFERENCES libraries(id))")

		dbc.commit()

# default behaviour.
def cmd_run(args):
	# transcode anything that's missing
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

#	Main
# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
if __name__ == "__main__":
	ap = argparse.ArgumentParser(description="Batch transcoding of audio files")
	subparsers = ap.add_subparsers()

	# list - prints out lists of things
	p_list = subparsers.add_parser("list", help="List different things")
	p_list.set_defaults(cmd="list")
	p_list.add_argument("--paths", "-p",
		type=str,
		dest="paths",
		metavar="LIBRARY",
		help="Lists the paths being watched under a specified library.")

	# library - configure libraries
	p_library = subparsers.add_parser("library", help="Configure libraries.")
	p_library.set_defaults(cmd="library")
	p_library.add_argument("--new", "-n",
		nargs=3,
		type=str,
		dest="new",
		metavar=("NAME", "SOURCE", "DESTINATION"),
		help="Creates a new library with source and destination root paths.")
	p_library.add_argument("--delete", "-d",
		type=str,
		dest="delete",
		metavar="NAME",
		help="Delete a library and its associated paths.")
	p_library.add_argument("--script-path", "-sp",
		nargs=2,
		type=str,
		dest="script",
		metavar=("LIBRARY", "PATH"),
		help="Set the transcoding script path for a library.")
	p_library.add_argument("--source-ext", "-se",
		nargs=2,
		type=str,
		dest="source_ext",
		metavar=("LIBRARY", "EXTENSION"),
		help="Set the source file extension. This should include the preceeding period. Example: for FLAC source audio files, set this extension to '.flac'")
	p_library.add_argument("--target-ext", "-te",
		nargs=2,
		type=str,
		dest="target_ext",
		metavar=("LIBRARY", "EXTENSION"),
		help="Set the target output file extension. This should include the preceeding period. Example: for MP3 output files, set this extension to '.mp3'")
	p_library.add_argument("--add-copy-ext", "-ace",
		nargs=2,
		type=str,
		dest="add_copy",
		metavar=("LIBRARY", "EXTENSION(S)"),
		help="Add copy extensions. Multiple extensions can be specified, separated by a comma. Copy extensions are a list of file extensions which files are to be copied over from the source to target tree. This could be used to copy image files so that album art is transfered over to the target directory.")
	p_library.add_argument("--clear-copy-ext", "-cce",
		type=str,
		dest="clear_copy",
		metavar="LIBRARY",
		help="Clears the copy extension list for a library. After calling this command no files will be copied over from the source to target tree.")

	# path operations
	p_path = subparsers.add_parser("path", help="Configure paths for a library.")
	p_path.set_defaults(cmd="path")
	p_path.add_argument("--add", "-a",
		nargs=2,
		type=str,
		dest="add",
		metavar=("LIBRARY", "PATH"),
		help="Adds a path to a library. Fails if the path given is not inside the libraries target path.")
	p_path.add_argument("--import", "-i",
		type=str,
		dest="import_paths",
		metavar="LIBRARY",
		help="Imports multiple paths to the specified library. Paths are read from the standard input stream with one path per line.")
	p_path.add_argument("--export", "-e",
		type=str,
		dest="export",
		metavar="LIBRARY",
		help="Exports the paths for the given library to a plaintext format which can then be read in again using 'path --import'.")
	p_path.add_argument("--remove", "-r",
		nargs=2,
		type=str,
		dest="remove",
		metavar=("LIBRARY", "PATH"),
		help="Remove a path from a library. Does not remove sub-paths under this path. Fails if the path does not exist in the library or if the library does not exist.")
	p_path.add_argument("--remove-tree", "-rt",
		nargs=2,
		type=str,
		dest="remove_tree",
		metavar=("LIBRARY", "PATH-PREFIX"),
		help="Removes all paths under PATH-PREFIX from a library.")

	# profile operations
	p_profile = subparsers.add_parser("profile", help="Configure profile.")
	p_profile.set_defaults(cmd="profile")
	p_profile.add_argument("--new", "-cp",
		action="store_true",
		dest="new",
		help="Creates a new blank profile. A profile contains all libraries, paths and settings for the application.")

	# run operations
	p_run = subparsers.add_parser("run", help="Run the transcoder.")
	p_run.set_defaults(cmd="run")

	args = ap.parse_args()
	settings = Settings.open()

	commands = {
		"library": cmd_library,
		"list": cmd_list,
		"path": cmd_path,
		"profile": cmd_profile,
		"run": cmd_run
	}
	commands[args.cmd](args)
	dbc.close()
