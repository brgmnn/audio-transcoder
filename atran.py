#!/usr/bin/env python

import multiprocessing, os, shutil, subprocess, sys, time, argparse, pickle, StringIO
import fnmatch, re, json, sqlite3
from sets import Set

atran_path = os.path.dirname(os.path.realpath(__file__))
dbc = None

#*		Settings
#*	holds the global settings for the transcoder.
#*~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~*#
class Settings:
	properties = {
		"default_copy_exts": [],
		"default_exts": [
			".wav",
			".mp3"
		],
		"default_script_path": "default-script.sh",
		"multithreaded": True,
		"cores": -1
	}

	@staticmethod
	def open():
		try:
			values = json.load(open(os.path.join(atran_path, "settings.json"), "rb"))
			Settings.properties = dict(Settings.properties.items() + values.items())
		except IOError:
			print >> sys.stderr, "Error: Failed to open one of the settings files. Attempting to \
				create it now..."
			Settings.save()
		return Settings.properties

	@staticmethod
	def save():
		try:
			Settings.properties["default_copy_exts"].sort()
			open(os.path.join(atran_path, "settings.json"), "wb").write(\
				json.dumps(Settings.properties, sort_keys=True, indent=4,\
					separators=(',', ': ')))
		except IOError:
			print >> sys.stderr, "Error: Failed to save settings."

#*		Path
#*	Really just to hold exceptions
#*~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~*#
class Path:
	class AlreadyExists(Exception):
		pass

#*		Library
#*	handles each library of audio files.
#*~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~*#
class Library:
	# Exceptions
	class NotFound(Exception):
		pass
	class OutsideSource(Exception):
		def __init__(self, source, path):
			self.source = source
			self.path = path
	class AlreadyExists(Exception):
		pass

	def __init__(self, *args, **kwargs):
		if len(args) == 1:
			# fetch an existing library from the database and create a new Library object for it.
			row = dbc.execute("SELECT * FROM libraries WHERE name=?", (args[0],)).fetchone()

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
				raise Library.NotFound
		elif len(args) == 2:
			# this is a temporary library to transcode everything in a folder.
			self.id = -1
			self.name = ":temporary-library:"
			self.source = os.path.abspath(args[0])
			self.target = os.path.abspath(args[1])
			self.paths = ["./"]
			self.script_path = Settings.properties["default_script_path"].encode('ascii', 'ignore')
			self.exts = [e for e in Settings.properties["default_exts"]]
			self.cexts = [e for e in Settings.properties["default_copy_exts"]]
		elif len(args) == 3:
			# create a new Library object and store it as a new library in the database.
			self.name = args[0]
			self.source = os.path.abspath(args[1])
			self.target = os.path.abspath(args[2])
			self.paths = []
			self.script_path = Settings.properties["default_script_path"].encode('ascii', 'ignore')
			self.exts = [e for e in Settings.properties["default_exts"]]
			self.cexts = [e for e in Settings.properties["default_copy_exts"]]

			self.save()
		else:
			# uninitialised library. used as a base to import a library to.
			self.id = -1
			self.name = ":uninitialised:"
			self.script_path = Settings.properties["default_script_path"].encode('ascii', 'ignore')
			self.exts = [e for e in Settings.properties["default_exts"]]
			self.cexts = [e for e in Settings.properties["default_copy_exts"]]

	def __str__(self):
		val = dbc.execute("SELECT COUNT(path) FROM paths WHERE lid=?", (self.id,)).fetchone()[0]
		return self.name+" ["+str(val)+" paths]\n" \
			+"  source dir  = "+self.source+"\n" \
			+"  target dir  = "+self.target+"\n" \
			+"  script path = "+self.script_path+"\n" \
			+"  source ext  = "+self.exts[0]+"\n" \
			+"  target ext  = "+self.exts[1]+"\n" \
			+"  copy exts   = "+", ".join(self.cexts);

	# adds a path to the library
	def add_path(self, path, check=True):
		if check:
			path = self.check_path(path)
		try:
			dbc.execute("INSERT INTO paths VALUES (NULL,?,?)", (self.id, path))
			dbc.commit()
		except sqlite3.IntegrityError:
			raise Path.AlreadyExists
		return 0

	# removes all paths under a given root directory
	def remove_path(self, path):
		path = self.check_path(path)
		dbc.execute("DELETE FROM paths WHERE lid=? AND path LIKE ?", (self.id, path+"%"))
		dbc.commit()
		return 0

	# remove a path from the library
	def remove_only_path(self, path):
		path = self.check_path(path)
		dbc.execute("DELETE FROM paths WHERE lid=? AND path=?", (self.id, path))
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
					(" ".join(new_cexts), self.id))
			elif "set" in kwargs:
				dbc.execute("UPDATE libraries SET copy_ext=? WHERE id=?", \
					(" ".join(kwargs["set"]), self.id))
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
			return path[3:]
		
		path = os.path.abspath(path)
		if not path.startswith(self.source):
			raise Library.OutsideSource(self.source, path)

		return os.path.relpath(path, self.source)

	# scan the directories for files
	def scan(self, force=False):
		tr = set()
		cp = set()
		tr_skip = 0
		cp_skip = 0

		if self.id >= 0:
			self.fetch_paths()

		for path in self.paths:
			src = os.path.join(self.source, path)

			if os.path.isfile(src):
				dst = os.path.join(self.target, path)

				if src[-len(self.exts[0]):] == self.exts[0]:
					dst = dst[:-len(self.exts[0])]+self.exts[1]
					if not os.path.isdir(os.path.dirname(dst)):
						os.makedirs(os.path.dirname(dst))
					
					if not os.path.exists(dst) or force:
						tr.add((src,dst))
					else:
						tr_skip += 1
				else:
					if not os.path.isdir(os.path.dirname(dst)):
						os.makedirs(os.path.dirname(dst))
					if not os.path.exists(dst) or force:
						cp.add((src,dst))
					else:
						cp_skip += 1
			else:
				for root, dirs, files in os.walk(src):
					files = [os.path.join(root, f) for f in files]
					sf = fnmatch.filter(files, "*"+self.exts[0])

					for c in self.cexts:
						sf.extend(fnmatch.filter(files, "*"+c))

					for s in sf:
						d = os.path.join(self.target, os.path.relpath(s, self.source))

						if s[-len(self.exts[0]):] == self.exts[0]:
							d = d[:-len(self.exts[0])]+self.exts[1]
							
							if not os.path.isdir(os.path.dirname(d)):
								os.makedirs(os.path.dirname(d))
							
							if not os.path.exists(d) or force:
								tr.add((s,d))
							else:
								tr_skip += 1
						else:
							if not os.path.isdir(os.path.dirname(d)):
								os.makedirs(os.path.dirname(d))
							if not os.path.exists(d) or force:
								cp.add((s,d))
							else:
								cp_skip += 1

		return (tr, cp, tr_skip, cp_skip)

	# transcode everything that needs to be in the library
	def transcode(self, workers, force=False):
		print "scanning for files..."
		tr, cp, tr_skip, cp_skip = self.scan(force)
		tr = sorted(list(tr))
		cp = sorted(list(cp))
		print "Found:"
		print "  transcode:",len(tr),"files ("+str(tr_skip)+" skipped)"
		print "  copy:     ",len(cp),"files ("+str(cp_skip)+" skipped)"

		if Settings.properties["multithreaded"]:
			p = workers.map_async(transcode_worker, [(self.script_path,)+p+(self.target,) for p in tr])
			try:
				p.get(0xffff)
			except KeyboardInterrupt:
				raise
		else:
			for src, dst in tr:
				transcode_worker(self.script_path, src, dst, self.target)

		for src, dst in cp:
			shutil.copy2(src,dst)
			print "c:",os.path.relpath(dst, self.target)

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

	# write the progress
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
		d["paths"] = self.fetch_paths()
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
		self.paths = d["paths"]

	# save a library into the SQL database
	def save(self):
		try:
			dbc.execute("INSERT INTO libraries VALUES (NULL,?,?,?,?,?,?,?)", (
				self.name,
				self.source,
				self.target,
				self.script_path,
				self.exts[0],
				self.exts[1],
				" ".join(self.cexts) ))
			self.id = dbc.execute("SELECT id FROM libraries WHERE name=?", \
				(self.name,)).fetchone()["id"]
			dbc.commit()
		except sqlite3.IntegrityError:
			raise Library.AlreadyExists

		for path in self.paths:
			self.add_path(path, False)

	# lists the names of all the libraries
	@staticmethod
	def list_names():
		return [n["name"] for n in dbc.execute("SELECT name FROM libraries ORDER BY name ASC")]

	# removes a library given its name
	@staticmethod
	def remove(name):
		try:
			lid = dbc.execute("SELECT id FROM libraries WHERE name=?", (name,)).fetchone()["id"]
			dbc.execute("DELETE FROM libraries WHERE name=?", (name,))
			dbc.execute("DELETE FROM paths WHERE lid=?", (lid,))
			dbc.commit()
			print "Deleted library '"+name+"'."
		except TypeError:
			raise Library.NotFound


#*		Public function, worker
#*~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~*#
# worker thread to transcode a single item
# tupe = (script_path, src, dst, drt)
def transcode_worker(tupe):
	try:
		devnull = open('/dev/null', 'w')
		p = subprocess.Popen([tupe[0],tupe[1],tupe[2]], stdout=devnull, stderr=devnull)
		p.wait()
		print "t:",os.path.relpath(tupe[2], tupe[3])
	except KeyboardInterrupt:
		pass

#*		Tool Commands
#*~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~*#
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
	elif args.export:
		# export a library to json
		print Library(args.export).json_encode()
	elif args.import_lib:
		# import a library from json
		json = sys.stdin.read()
		lib = Library()
		lib.json_decode(json)
		lib.save()

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
		while True:
			try:
				path = raw_input()
				if path == "":
					break
				try:
					lib.add_path(path)
				except Library.OutsideSource:
					print >> sys.stderr, "Error: Path is outside of the library source path."
				except Path.AlreadyExists:
					print >> sys.stderr, "Error: Path already in library database!"
			except EOFError:
				break
	elif args.export:
		# export paths from a library
		Library(args.export).export_paths()
	elif args.remove:
		# remove paths from a library
		name, path = args.remove
		Library(name).remove_path(path)
	elif args.remove_only:
		# remove a path from a library
		name, path = args.remove_only
		Library(name).remove_only_path(path)

# at the moment just to initialise the profile database.
def cmd_config(args):
	if args.newdb:
		# creates a new database profile. will delete the contents of an existing "profile.db3"!
		fp = open(os.path.join(atran_path, "profile.db3"), "rw+")
		fp.truncate()
		fp.close()
		
		dbc = sqlite3.connect(os.path.join(atran_path, "profile.db3"))
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
		print "New profile database successfully created."

# default behaviour.
def cmd_run(args):
	# transcode anything that's missing
	print "--- Audio Transcoder ---"
	print "  Workers: "+str(multiprocessing.cpu_count())
	print
	
	workers = []
	if Settings.properties["multithreaded"]:
		if Settings.properties["cores"] > 1:
			workers = multiprocessing.Pool(Settings.properties["cores"])
		else:
			workers = multiprocessing.Pool()
	
	if len(args.todo) == 1:
		# only process a specific library
		lib = Library(args.todo[0])
		print "  [",args.todo[0],"]"
		lib.clean_tree()
		lib.transcode(workers, args.force)
	elif len(args.todo) == 2:
		# process this as a source, target directory and process all files in it.
		# only process a specific library
		lib = Library(args.todo[0], args.todo[1])
		lib.clean_tree()
		lib.transcode(workers, args.force)
	else:
		# process all libraries
		for name in sorted(Library.list_names()):
			lib = Library(name)
			print "  [",name,"]"
			lib.clean_tree()
			lib.transcode(workers, args.force)

	if Settings.properties["multithreaded"]:
		workers.close()
		workers.join()

#*		Main
#*~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~*#
if __name__ == "__main__":
	ap = argparse.ArgumentParser(description="Batch transcoding of audio files")
	subparsers = ap.add_subparsers()

	#*	Assign arguments
	#*~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~*#
	# list - prints out lists of things
	p_list = subparsers.add_parser("list", help="List different things")
	p_list.set_defaults(cmd="list")
	p_list.add_argument("--paths", "-p",
		type=str,
		dest="paths",
		metavar="LIBRARY",
		help="Lists the paths associated with the named library.")

	# library - configure libraries
	p_library = subparsers.add_parser("library", help="Configure libraries.")
	p_library.set_defaults(cmd="library")
	p_library.add_argument("--new", "-n",
		nargs=3,
		type=str,
		dest="new",
		metavar=("LIBRARY", "SOURCE", "DESTINATION"),
		help="Creates a new library with source and destination root paths.")
	p_library.add_argument("--delete", "-d",
		type=str,
		dest="delete",
		metavar="LIBRARY",
		help="Delete a library and its associated paths.")
	p_library.add_argument("--script-path", "-sp",
		nargs=2,
		type=str,
		dest="script",
		metavar=("LIBRARY", "PATH"),
		help="Set the script path for a library.")
	p_library.add_argument("--source-ext", "-se",
		nargs=2,
		type=str,
		dest="source_ext",
		metavar=("LIBRARY", "EXTENSION"),
		help="Set the source file extension for a library. This should include the preceeding \
			period. Example: for FLAC source audio files, set this extension to '.flac'")
	p_library.add_argument("--target-ext", "-te",
		nargs=2,
		type=str,
		dest="target_ext",
		metavar=("LIBRARY", "EXTENSION"),
		help="Set the target output file extension for a library. This should include the \
			preceeding period. Example: for MP3 output files, set this extension to '.mp3'")
	p_library.add_argument("--add-copy-ext", "-ace",
		nargs=2,
		type=str,
		dest="add_copy",
		metavar=("LIBRARY", "EXTENSION(S)"),
		help="Add copy extensions to a library. Multiple extensions can be specified, separated by \
			a comma. Copy extensions are a list of file extensions which files are to be copied \
			over from the source to target tree. This could be used to copy image files so that \
			album art is transfered over to the target directory.")
	p_library.add_argument("--clear-copy-ext", "-cce",
		type=str,
		dest="clear_copy",
		metavar="LIBRARY",
		help="Clears the copy extension list for a library. After calling this command no files \
			will be copied over from the source to target tree.")
	p_library.add_argument("--export", "-e",
		type=str,
		dest="export",
		metavar="LIBRARY",
		help="Export a library to JSON format.")
	p_library.add_argument("--import", "-i",
		action="store_true",
		dest="import_lib",
		help="Import a library from JSON format.")

	# path operations
	p_path = subparsers.add_parser("path", help="Configure paths for a library.")
	p_path.set_defaults(cmd="path")
	p_path.add_argument("--add", "-a",
		nargs=2,
		type=str,
		dest="add",
		metavar=("LIBRARY", "PATH"),
		help="Adds a path to a library. Fails if the path given is not inside the libraries target \
			path.")
	p_path.add_argument("--import", "-i",
		type=str,
		dest="import_paths",
		metavar="LIBRARY",
		help="Imports multiple paths to a library. Paths are read from the standard input stream \
			with one path per line.")
	p_path.add_argument("--export", "-e",
		type=str,
		dest="export",
		metavar="LIBRARY",
		help="Exports the paths for a library to a plaintext format which can then be read in \
			again using 'path --import'.")
	p_path.add_argument("--remove", "-r",
		nargs=2,
		type=str,
		dest="remove",
		metavar=("LIBRARY", "PATH"),
		help="Remove a path from a library.")
	p_path.add_argument("--remove-only", "-ro",
		nargs=2,
		type=str,
		dest="remove_only",
		metavar=("LIBRARY", "PATH"),
		help="Removes exactly the path from the library. Doesn't remove sub-paths under this path.")

	# config operations
	p_config = subparsers.add_parser("config", help="Configure config.")
	p_config.set_defaults(cmd="config")
	p_config.add_argument("--new-db",
		action="store_true",
		dest="newdb",
		help="Creates a new database profile. The database profile contains all libraries, paths \
			and settings for the application.")

	# run operations
	p_run = subparsers.add_parser("run", help="Run the transcoder.")
	p_run.set_defaults(cmd="run")
	p_run.add_argument("--force", "-f",
		action="store_true",
		dest="force",
		help="Force all scanned files to be processed even if there is already a target file for \
			it.")
	p_run.add_argument("todo",
		nargs="*",
		type=str,
		help="What should the transcoder do. Specify either a library or a source and target \
			directory and the transcoder will process those (with the default settings in \
			settings.json for a path tuple). Leave empty to process all libraries.")

	#*	Parse arguments, open settings, open database etc.
	#*~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~*#
	args = ap.parse_args()
	settings = Settings.open()

	# check if the database exists, if it doesn't create a new one automatically, otherwise just
	# open it
	if not os.path.exists(os.path.join(atran_path, "profile.db3")):
		print >> sys.stderr, "Warning: No database file 'profile.db3' found. Creating a new \
			database..."
		dbc = sqlite3.connect("profile.db3")
		ndb = argparse.Namespace()
		ndb.newdb = True
		cmd_config(ndb)
	else:
		dbc = sqlite3.connect(os.path.join(atran_path, "profile.db3"))
	dbc.row_factory = sqlite3.Row

	# commands dictionary holding pointer to the functions
	commands = {
		"library": cmd_library,
		"list": cmd_list,
		"path": cmd_path,
		"config": cmd_config,
		"run": cmd_run
	}
	
	#*	Try and run, catch exceptions
	#*~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~*#
	try:
		commands[args.cmd](args)
	except Library.AlreadyExists:
		print >> sys.stderr, "Error: A library with that name already exists."
	except Library.NotFound:
		print >> sys.stderr, "Error: No library with that named in the database."
	except Library.OutsideSource as e:
		print >> sys.stderr, "Error: Path is outside of the library source path."
		print >> sys.stderr, "  source =",e.source
		print >> sys.stderr, "  path =",e.path
	except Path.AlreadyExists:
		print >> sys.stderr, "Error: Path already in library database!"
	except KeyboardInterrupt:
		print >> sys.stderr
		print >> sys.stderr, "Terminated early from user input."
		# todo: make this work for multiprocessing
	except sqlite3.OperationalError as e:
		print >> sys.stderr, "Error: Sqlite3 encountered a operational error: '"+str(e)+"'"

	dbc.close()


