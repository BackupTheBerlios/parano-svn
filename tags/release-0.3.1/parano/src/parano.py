#!/usr/bin/env python

# Parano - GNOME HashFile Frontend
# Copyright (C) 2005-2006 Gautier Portet < kassoulet users.berlios.de >

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

NAME="Parano"
VERSION="@version@"
DATADIR="@datadir@"
URL="http://parano.berlios.de"

import os, sys, time, re, thread
import pygtk
pygtk.require('2.0')
import gobject, gtk, gtk.glade, gnome, gnome.ui, gnomevfs
import cStringIO, traceback
import urllib
import gettext
_=gettext.gettext

import md5
import zlib
import sha

def gtk_iteration():
	"""launch one loop of gtk_main_iteration"""
	while gtk.events_pending():
		gtk.main_iteration(False)

def auto_connect(object_to_connect, dialog):
	"""automatically connect glade dialog widgets with python object"""
	for widget in dialog.get_widget_prefix(''):
		name = widget.get_name()
		assert not hasattr(object_to_connect, name), name
		setattr(object_to_connect, name, widget)

option_quiet = False

def log(*args):
	"""print a message"""
	if not option_quiet:
		print " ".join([str(a) for a in args])
		
def debug(*args):
	"""print a debug message"""
	#print " ".join([str(a) for a in args])
	pass

def vfs_get_protocol(uri):
	"""return the protocol used in the uri"""
	protocol, tmp = uri.split(":")
	return protocol

def vfs_clean_uri(uri):
	"""return an uri from an uri or a local path"""
	try:
		gnomevfs.URI(uri)
		gnomevfs.Handle(uri)
	except : #gnomevfs.InvalidURIError:
		# maybe a local path ?
		local = os.path.abspath(uri)
		if os.path.exists(local):
			uri = gnomevfs.get_uri_from_local_path(local)
		uri = gnomevfs.escape_host_and_path_string(uri)
	return uri

def vfs_open(uri, mode="r"):
	"""return a file() compatible object from an uri"""
	uri = vfs_clean_uri(uri)
	uri = gnomevfs.URI(uri)
	f = gnomevfs.Handle(uri)
	return f

def vfs_walk(uri):
	"""in the style of os.path.walk, but using gnomevfs.
	
	uri -- the base folder uri.
	return a list of uri.
	"""
	if not isinstance(uri, gnomevfs.URI):
		uri = gnomevfs.URI(uri)
	if str(uri)[-1] != '/':
		uri = uri.append_string("/")
	filelist = []	
	try:
		dirlist = gnomevfs.open_directory(uri)
	except:
		log(_("skipping: '%s'") % uri)
		return filelist
		
	for file_info in dirlist:
		if file_info.name[0] == ".":
			continue
	
		if file_info.type == gnomevfs.FILE_TYPE_DIRECTORY:
			filelist.extend(
				vfs_walk(uri.append_path(file_info.name)) )

		if file_info.type == gnomevfs.FILE_TYPE_REGULAR:
			filelist.append( str(uri.append_file_name(file_info.name)) )
	return filelist

def vfs_makedirs(path_to_create):
	"""Similar to os.makedirs, but with gnomevfs"""
	
	uri = gnomevfs.URI(path_to_create)
	path = uri.path

	# start at root
	uri =  uri.resolve_relative("/")
	
	for folder in path.split("/"):
		if not folder:
			continue
		uri = uri.append_string(folder)
		try:
			gnomevfs.make_directory(uri, 0777)
		except gnomevfs.FileExistsError:
			pass
		except:
			return False
	return True	


COLUMN_ICON=0
COLUMN_FILE=1

BUFFER_SIZE=1024*64

HASH_DIFFERENT=0	# hash is not what expected: file corrupted !
HASH_MISSING=1		# file is missing
HASH_ERROR=2		# cannot check hash
HASH_OK=3			# hash is as excepted
HASH_NOT_CHECKED=4	# hash not checked yet

icons = {
	HASH_NOT_CHECKED	:  None,
	HASH_OK			: gtk.STOCK_APPLY,
	HASH_ERROR		: gtk.STOCK_DIALOG_WARNING,
	HASH_DIFFERENT	: gtk.STOCK_DIALOG_ERROR,
	HASH_MISSING	: gtk.STOCK_MISSING_IMAGE	
}

STATE_READY,STATE_HASHING,STATE_CORRECT,STATE_CORRUPTED = range(4)

status_icons = {
	STATE_READY	:  None,
	STATE_HASHING	: gtk.STOCK_REFRESH,
	STATE_CORRECT	: gtk.STOCK_DIALOG_AUTHENTICATION,
	STATE_CORRUPTED	: gtk.STOCK_DIALOG_ERROR,
}


class File:
	# File contained in hash file
	def __init__(self, filename="", displayed_name="", expected_hash="", size=0):
		if displayed_name:
			self.displayed_name=displayed_name
		else:
			self.displayed_name=os.path.split(filename)[1]
		self.displayed_name = gnomevfs.unescape_string_for_display(self.displayed_name)	
		self.filename=filename
		# the Hash loaded from file
		self.expected_hash=expected_hash
		# the Hash calculated
		self.real_hash=""
		# the file size
		self.size=size
		self.status=HASH_NOT_CHECKED

		if not size:
			try:
				info = gnomevfs.get_file_info(self.filename, gnomevfs.FILE_INFO_FIELDS_SIZE)
				self.size = info.size
			except:
				log(_("Warning: cannot get size of file '%s'") % filename)
				self.size = 0;

class HasherMD5:
	def init(self):
		self.hasher = md5.new()
		
	def update(self, data):
		self.hasher.update(data)
		
	def get_hash(self):
		return self.hasher.hexdigest()

class HasherSHA1:
	def init(self):
		self.hasher = sha.new()
		
	def update(self, data):
		self.hasher.update(data)
		
	def get_hash(self):
		return self.hasher.hexdigest()

class HasherCRC32:
	def init(self):
		self.crc = zlib.crc32("")
		
	def update(self, data):
		self.crc = zlib.crc32(data,self.crc)
		
	def get_hash(self):
		if self.crc < 0: # wtf? 
			self.crc = -(self.crc^0xffffffff)-1
		return "%08X" % self.crc

class FormatBase:
	def detect_file(self, f):
		
		for line in f:
			line = line.strip()
			result = self.regex_reader.search(line)
			if result:
				# parse is ok
				hash = result.group("hash")
				file = result.group("file")
				if hash and file:
					# a line with valid content
					return True
		return False
		
	def read_file(self, f):
		list = []

		for line in f:
			line = line.strip()
			result = self.regex_reader.search(line)
			if result:
				# parse is ok
				hash = result.group("hash")
				file = result.group("file")
				if hash and file:
					# a line with valid content
					list.append( (hash, file) )
		return list

	def write_file(self, f, list):
		comment = "Created by %s %s - %s" % (NAME, VERSION, URL)
		f.write(self.format_comment % comment)
		for hash, file in list:
			f.write(self.format_writer % locals())

class FormatMD5 (FormatBase):
	def __init__(self):
		self.name = "MD5"
		self.filename_pattern = "*.md5*"
		self.filename_regex = re.compile(r".*\.md5(sum)?")
		self.hasher = HasherMD5()

		self.regex_reader = re.compile(r";.*|#.*|\\?^(?P<hash>[\dA-Fa-f]{32}) [\* ]?(?P<file>.*$)\\?|^\s*$")
		self.format_writer = "%(hash)s *%(file)s\n" 
		self.format_comment= "; %s\n"

class FormatSHA1 (FormatBase):
	def __init__(self):
		self.name = "SHA-1"
		self.filename_pattern = "*.sha1*"
		self.filename_regex = re.compile(r".*\.sha1(sum)?")
		self.hasher = HasherSHA1()

		self.regex_reader = re.compile(r";.*|#.*|\\?^(?P<hash>[\dA-Fa-f]{40}) [\* ]?(?P<file>.*$)\\?|^\s*$")
		self.format_writer = "%(hash)s *%(file)s\n" 
		self.format_comment= "; %s\n"

class FormatSFV (FormatBase):
	def __init__(self):
		self.name = "SFV"
		self.filename_pattern = "*.sfv"
		self.filename_regex = re.compile(r".*\.sfv")
		self.hasher = HasherCRC32()

		self.regex_reader = re.compile(r";.*|(?P<file>.*) (?P<hash>[\dA-Fa-f]{8}$)|^\s*$")
		self.format_writer = "%(file)s %(hash)s\n"
		self.format_comment= "; %s\n"

formats = (FormatMD5(), FormatSFV(), FormatSHA1())

class Parano:
	
	def get_file_hash(self, uri):
		# compute hash of given file
		try:
			f = vfs_open(uri)
		except gnomevfs.NotFoundError: 
			log( _("Cannot read file: '%s'") % uri)
			return ""
		except gnomevfs.AccessDeniedError:
			log( _("Cannot access file: '%s'") % uri)
			return ""
		
		hasher = self.format.hasher
		hasher.init()
		
		while 1:
			while self.paused:
				# paused, wait forever
				gtk_iteration()
				time.sleep(0.1)
			if self.abort:
				return "aborted"
		
			try:
				data = f.read(BUFFER_SIZE)
			except :
				break
			hasher.update(data)
			self.progress_current_bytes=self.progress_current_bytes+BUFFER_SIZE

		f.close()
		return hasher.get_hash()

	def new_hashfile(self):
		# reset hashfile
		self.filename=""
		self.files=[]
		self.total_size=0
		self.liststore.clear()
		self.modified=False
		self.update_title()
		self.set_status(_("Ready"))

	def get_hashfile_format(self, uri, content):
	
		for format in formats:
			# search in al our recognized formats
			regex = format.filename_regex
			result = regex.search(uri.lower())
			if result:
				# this can be a valid filename, now look inside
				if format.detect_file(content):
					# yes, this is a valid hashfile \o/
					return format
		return None

	def load_hashfile(self, uri):
		# load hashfile
		uri = vfs_clean_uri(uri)
		content = gnomevfs.read_entire_file(uri)
		lines = content.split("\n")
		
		files_to_add=[]
		self.format=self.get_hashfile_format(uri, lines)
				
		if not self.format:
			log("unknown format")
			return
		log("Detected format: " + self.format.name)
				
		list = self.format.read_file(lines)

		root = os.path.dirname(uri)
		
		for hash, file in list:
			absfile = os.path.join(root, file)
			u = gnomevfs.escape_host_and_path_string(absfile)
			files_to_add.append( (u, file, hash) )
		
		# reset hashfile
		self.new_hashfile()
		
		# do add the files to list
		for f in files_to_add:
			self.files.append(File(f[0], f[1], f[2]))
		
		self.filename=uri
		self.update_hashfile()
		self.update_ui()
		self.update_and_check_file_list()
		return True

	def get_relative_filename(self, uri, ref):
		""" return the relative filename to reach uri from ref
		ref must be a folder path (ie: strip the filename.md5)
		"""

		if not uri.startswith(ref.split(":")[0]):
			return None

		relative = []
		u = uri.split("/")
		r = ref.split("/")
		remove = 0
		for i in xrange(min(len(u), len(r))):
			if u[i] != r[i]:
				break
			remove += 1
		u = u[remove:]
		r = r[remove:]
		for i in r:
			if i:
				relative.append("..")
		for i in u:
			if i:
				relative.append(i)
		return "/".join(relative)
		

	def save_hashfile(self, uri):

		for format in formats:
			regex = format.filename_regex
			result = regex.search(uri)
			if result:
				self.format = format
				log("Saving with format:", format.name)
				break

		self.update_hashfile()
		if self.abort:
			return

		list=[]
		base = os.path.dirname(uri)
		remove = len(base)+1
		for ff in self.files:
			# convert to a path relative to hashfile
			dest = self.get_relative_filename(ff.filename, base)
			if not dest:
				self.set_status(_("Cannot save hashfile"))
				log("Cannot save hashfile '%s'" % ff.filename)
				return
			file = gnomevfs.unescape_string_for_display(dest)
			hash = ff.real_hash
			list.append( (hash,file) )
			
		u = gnomevfs.URI(uri)
		log("saving to:", u)
		f = gnomevfs.create(u , gnomevfs.OPEN_WRITE)
		self.format.write_file(f, list)
		f.close()
		
		self.modified=False
		self.filename=uri
		self.update_title()
		self.set_status(_("Hashfile Saved"))

	def add_file(self, filename, displayed_name=None, hash=None):
	
		info = gnomevfs.get_file_info(filename, gnomevfs.FILE_INFO_FIELDS_SIZE)

		if info.type == gnomevfs.FILE_TYPE_REGULAR:
			self.files.append(File(filename, displayed_name, hash))
		elif info.type == gnomevfs.FILE_TYPE_DIRECTORY:
			self.add_folder(filename)
		else:
			log("error when trying to add: '%s'" % filename)

	def set_status(self, text, icon=STATE_READY):
		self.status_text = text
		self.status_icon = icon
		self.statusbar.set_text(text)
		if self.status_icon == STATE_READY:
			self.statusicon.set_from_pixbuf(None)
		else:
			self.statusicon.set_from_stock(status_icons[icon], gtk.ICON_SIZE_BUTTON)

	def update_ui(self):
		self.update_title()
		self.update_file_list()

	def update_title(self):
		
		if self.filename != "":
			title = os.path.basename(self.filename)
		else:
			if self.modified:
				title = _("Untitled Hashfile (Unsaved)")
			else:
				title = _("Untitled Hashfile")
			
		self.window_main.set_title(title)

	def on_update_hash_cancel(self, widget):
		self.paused = False
		self.abort = True	

	def on_update_hash_pause(self, widget):
		self.paused = not self.paused
		if self.paused:
			self.progresslabel.set_markup(_("<i>%s (Paused)</i>") % gobject.markup_escape_text(self.current_file))
			self.progressbar.set_text(_("Paused"))

	def thread_update_hash(self):
	
		for f in self.files:
			if self.abort:
				# cancel button pressed
				break

			# for progress
			self.current_file = os.path.basename(f.filename)
			
			f.real_hash = self.get_file_hash(f.filename)
			self.progress_file=self.progress_file+1
			
			if not f.expected_hash:
				# new file in md5
				f.status = HASH_OK
			else:	
				#print self.current_file, f.real_hash, f.expected_hash
				if f.real_hash.lower() == f.expected_hash.lower():
					# matching md5
					f.status = HASH_OK
				else:
					if not f.real_hash:
						if gnomevfs.exists(f.filename):
							# cannot read file
							f.status = HASH_ERROR
						else:
							# file is missing
							f.status = HASH_MISSING
					else:
						# md5 mismatch
						f.status = HASH_DIFFERENT

		# stop progress
		self.progress_total_bytes=0


	def update_hashfile(self):

		if not self.files:
			return

		self.set_status(_("Hashing..."), STATE_HASHING)
		glade = os.path.join(DATADIR, "parano.glade")
		sensitive_widgets = ("menubar","toolbar","filelist")
		for w in sensitive_widgets:
			self.window.get_widget(w).set_sensitive(False)

		events = { 
					"on_button_cancel_clicked" : self.on_update_hash_cancel,
					"on_button_pause_clicked" : self.on_update_hash_pause 
		}
		self.window.signal_autoconnect(events)
		self.progressbar = self.window.get_widget("progressbar")
		self.progresslabel = self.statusbar
		progress = self.window.get_widget("progress_frame")
		self.window.get_widget("button_pause").show()

		self.progresslabel.set_markup("")
		progress.show()

		gtk_iteration()

		self.abort = False
		self.paused = False
		
		self.progress_nbfiles=len(self.files)
		self.progress_file=0
		self.current_file=""

		self.progress_total_bytes=1L
		for f in self.files:
			self.progress_total_bytes=self.progress_total_bytes+f.size
		self.progress_current_bytes=0L

		start=time.time()
		total = self.progress_total_bytes
		thread.start_new_thread(self.thread_update_hash, ())
		
		while self.progress_total_bytes>0:
			if self.abort:
				self.progressbar.set_text(_("Canceling..."))
				break
			if not self.paused:
				now=time.time()
				self.progresslabel.set_markup(_("Hashing file <b>%d</b> of <b>%d</b>: <i>%s</i>") % (self.progress_file, self.progress_nbfiles, gobject.markup_escape_text(gnomevfs.unescape_string_for_display(self.current_file))))
				fraction = float(self.progress_current_bytes) / float(self.progress_total_bytes)
				fraction2= float(self.progress_file) / float(self.progress_nbfiles)
				fraction = (fraction + fraction2) / 2.0
				if fraction>1.0:
					fraction=1.0
				self.progressbar.set_fraction(fraction)
				if fraction>0.0:
					remaining = int((now-start)/fraction-(now-start))
					minutes = remaining/60.0
					seconds = remaining%60
					if minutes >= 1:
						text = _("About %d:%02d minute(s) remaining") % (minutes, seconds)
						#text = _("About %d minute(s) remaining") % minutes
					else:
						text = _("Less than one minute remaining")
					self.progressbar.set_text(text)
				
			gtk_iteration()
			time.sleep(0.1)

		progress.hide()	
		if self.abort:
			self.update_file_list()
			log(_("Hashing canceled!"))
			self.set_status(_("Hashing canceled!"))
		else:
			self.update_and_check_file_list()
			self.set_status(_("%d files verified and ok. (%.2f MiB)") % (len(self.files), total/1024.0/1024.0), STATE_CORRECT)
			log( "hashed %d file(s) at %.2f MiB/s" % (len(self.files),total/(time.time()-start)/(1024*1024)))

		self.window_main.set_sensitive(True)
		for w in sensitive_widgets:
			self.window.get_widget(w).set_sensitive(True)

	def update_file_list(self):  
		self.liststore.clear()
		changed, missing, error = 0,0,0

		common = os.path.commonprefix([f.displayed_name for f in self.files])		
		debug("update file list")

		# sort by status
		self.files.sort(key=lambda x: x.status)

		for f in self.files:
			iter = self.liststore.append()
			#self.liststore.set(iter, COLUMN_FILE, f.displayed_name[len(common):])
			self.liststore.set(iter, COLUMN_FILE, f.displayed_name)
			self.liststore.set(iter, COLUMN_ICON, icons[f.status])
			if f.status == HASH_DIFFERENT:
				changed += 1
			if f.status == HASH_MISSING:
				missing += 1
			if f.status == HASH_ERROR:
				error += 1
		return changed, missing, error

	def update_and_check_file_list(self):
		changed, missing, error = self.update_file_list()
		if changed or missing or error:
			self.set_status(_("Warning: %d files are different!") % (changed+missing+error),STATE_CORRUPTED)
		else:
			if not self.files:
				self.set_status(_("Ready."))

	def on_quit_activate(self, widget):
		if not self.on_delete_event(widget):
			gtk.main_quit()

	def discard_hashfile(self):
		# display a dialog asking the user if he want to save
		# but only if the hashfile was modified
		# return True if we can discard hashfile contents
		# return False if we cannot touch hashfile contents
		
		if self.modified and len(self.files)>0:
			glade = os.path.join(DATADIR, "parano.glade")
			dialog = gtk.glade.XML(glade,"dialog_save_changes")\
						.get_widget("dialog_save_changes")
			result = dialog.run()
			dialog.hide_all()
			if result == gtk.RESPONSE_OK:
				# save before continue
				self.on_save_hashfile_activate(None)
				if self.modified: 
					# hashfile still marked as modified, so saving was canceled
					return False
				else:
					# hashfile saved
					return True
			elif result == gtk.RESPONSE_CANCEL:
				# cancel operation
				return False
			elif result == gtk.RESPONSE_CLOSE:
				# don't save and continue
				return True
		return True

	def on_delete_event(self, widget, event=None, data=None):
		# Change FALSE to TRUE and the main window will not be destroyed
		# with a "delete_event".
		
		if self.discard_hashfile():
			return False 
		else:
			return True

	def on_destroy(self, widget, data=None):
		gtk.main_quit()
		
	def on_about_activate(self, widget):
		# about dialog
		glade = os.path.join(DATADIR, "parano.glade")
		about_dialog = gtk.glade.XML(glade,"dialog_about")
		dialog = about_dialog.get_widget("dialog_about")
		dialog.set_property("name",NAME)
		dialog.set_property("version",VERSION)

	def on_new_hashfile_activate(self, widget):
		# new_hashfile
		if self.discard_hashfile():
			self.new_hashfile()

	def on_load_hashfile_activate(self, widget):
		# load_hashfile dialog

		if not self.discard_hashfile():
			return

		glade = os.path.join(DATADIR, "parano.glade")
		self.loadhashfile_dialog = gtk.glade.XML(glade,"filechooserdialog_loadhashfile")
		dialog = self.loadhashfile_dialog.get_widget("filechooserdialog_loadhashfile")

		filter = gtk.FileFilter()
		
		for format in formats:
			filter.add_pattern(format.filename_pattern)

		dialog.set_filter(filter)

		result = dialog.run()
		dialog.hide_all()
		gtk_iteration()
		
		if result == gtk.RESPONSE_OK:
			self.load_hashfile(dialog.get_uri())
	
		self.update_file_list()

		
	def on_save_hashfile_activate(self, widget):
		# save_hashfile dialog
		if self.filename == "":
			self.on_save_as_hashfile_activate(widget)
		else:
			self.save_hashfile(self.filename)

	def on_save_as_hashfile_activate(self, widget):
		# save_as_hashfile dialog
		glade = os.path.join(DATADIR, "parano.glade")
		self.savehashfile_dialog = gtk.glade.XML(glade,"filechooserdialog_savehashfile")
		dialog = self.savehashfile_dialog.get_widget("filechooserdialog_savehashfile")
		
		filter = gtk.FileFilter()
		for format in formats:
			filter.add_pattern(format.filename_pattern)
		dialog.set_filter(filter)
		
		result = dialog.run()
		dialog.hide_all()
		gtk_iteration()
		if result == gtk.RESPONSE_OK:
			self.filename = dialog.get_uri()
			self.update_title()

			if os.path.exists(self.filename):
				glade = os.path.join(DATADIR, "parano.glade")
				dialog_ow = gtk.glade.XML(glade,"dialog_overwrite_file")\
							.get_widget("dialog_overwrite_file")
				result = dialog_ow.run()
				dialog_ow.hide_all()
				gtk_iteration()
				if result == gtk.RESPONSE_CANCEL:
					# cancel
					return
			self.save_hashfile(self.filename)
	

	def on_addfile_activate(self, widget):
		# addfile dialog
		glade = os.path.join(DATADIR, "parano.glade")
		self.addfile_dialog = gtk.glade.XML(glade,"filechooserdialog_addfile")
			
		dialog = self.addfile_dialog_dlg = self.addfile_dialog.get_widget("filechooserdialog_addfile")
		result = dialog.run()
		if result == gtk.RESPONSE_OK:
			for f in dialog.get_uris():
				self.add_file(f)
	
		self.update_file_list()
		dialog.hide_all()
		self.modified=True
		self.update_title()
		
	def on_addfolder_activate(self, widget):
		# addfolder dialog
		glade = os.path.join(DATADIR, "parano.glade")
		self.addfolder_dialog = gtk.glade.XML(glade,"filechooserdialog_addfolder")

		dialog = self.addfolder_dialog_dlg = self.addfolder_dialog.get_widget("filechooserdialog_addfolder")

		result = dialog.run()
		dialog.hide_all()
		gtk_iteration()
	
		if result == gtk.RESPONSE_OK:
			uris = dialog.get_uris()
			base = os.path.commonprefix(uris)
			for uri in uris:
				self.add_folder(uri, base)
			
		gtk_iteration()

	def add_folder_thread(self, folder, prefix):
		files = []
		self.current_file = _("Reading list of files...") 
		for uri in vfs_walk(folder):
			files.append(uri)
	
		if not prefix:
			prefix = os.path.commonprefix(files)
			
		if prefix[-1] != "/":
			prefix = prefix + "/"
			
		visible = 0
		if prefix:
			visible = len(prefix)

		for uri in files:
			self.add_file(uri, gnomevfs.unescape_string_for_display(uri[visible:]))
			if self.abort:
				break
		self.adding_folders = False

	def add_folder(self, folder, prefix=None):
		log("adding folder:", folder)
		glade = os.path.join(DATADIR, "parano.glade")
		self.progress_dialog = gtk.glade.XML(glade,"addfolder_progress")
		
		events = { "on_button_cancel_clicked" : self.on_addfolder_cancel }
		self.window.signal_autoconnect(events)
		
		progressbar = self.window.get_widget("progressbar")
		progresslabel = self.statusbar
		progress = self.window.get_widget("progress_frame")
		self.window.get_widget("button_pause").hide()
		
		self.adding_folders=True
		self.abort=False
		progress.show()	
		self.current_file=""
		self.set_status(_("Listing files...."), STATE_HASHING)
		
		# save current files list
		backup = self.files[:]
		t=0

		thread.start_new_thread(self.add_folder_thread, (folder,prefix))
		
		while(self.adding_folders):
			progresslabel.set_markup("<small><i>%s</i></small>" % gnomevfs.unescape_string_for_display(self.current_file))
			progressbar.pulse()
			gtk_iteration()
			time.sleep(0.1)

		if not self.abort:
			self.modified=True
			self.update_ui()

		if self.abort:
			# restore original file list
			self.files = backup
			self.set_status(_("Add Folder canceled."))
		else:
			self.set_status(_("Ready."))
		progress.hide()	

	def on_remove_activate(self, widget):
		
		def cb_treelist(model, path, iter, list):
			list.append(iter)	
			
		selection = self.filelist.get_selection()
		list = []
		selection.selected_foreach(cb_treelist, list)
	
		for i in list:
			self.liststore.remove(i)

	def on_addfolder_cancel(self, widget):
		self.abort=True	
			
	def on_refresh(self, widget):
		for f in self.files:
			f.status = HASH_NOT_CHECKED
		self.update_hashfile()

	def init_window(self):
		# main window
		glade = os.path.join(DATADIR, "parano.glade")
		self.window = window = gtk.glade.XML(glade,"window_main")
		window.signal_autoconnect(self)
		auto_connect(self, window)

		# file list
		self.filelist = filelist = window.get_widget("filelist")
		filelist.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
		
		# icon column
		renderer = gtk.CellRendererPixbuf()
		renderer.set_property("stock-id", gtk.STOCK_MISSING_IMAGE)
		column = gtk.TreeViewColumn("Status", renderer)
		column.set_sort_column_id(COLUMN_ICON)
		column.set_sort_indicator(True)
		column.set_sort_order(gtk.SORT_ASCENDING)
		column.add_attribute(renderer, "stock_id", COLUMN_ICON)
		filelist.append_column(column)

		# filename column
		column = gtk.TreeViewColumn("File", gtk.CellRendererText(),
		                            text=COLUMN_FILE)
		column.set_sort_column_id(COLUMN_FILE)
		filelist.append_column(column)

		self.liststore = gtk.ListStore(gobject.TYPE_STRING,gobject.TYPE_STRING)
		filelist.set_model(self.liststore)

		# status bar
		self.statusbar = window.get_widget("statusbar")
		self.statusbar = window.get_widget("label_status")

		self.statusicon = window.get_widget("image_status")
		self.statusicon.set_from_pixbuf(None)

		# we accept dropped files
		filelist.drag_dest_set(gtk.DEST_DEFAULT_ALL,[
			('text/uri-list',0,0),
			('text/plain',0,0),
			('STRING',0,0)],
			gtk.gdk.ACTION_COPY|gtk.gdk.ACTION_MOVE)

	def on_filelist_drag_data_received(self, widget, drag_context, x, y, selection_data, info, timestamp):
		
		files = selection_data.data.split()
		drag_context.drop_finish(True, timestamp)
		
		for f in files:
			# remove trailing noise
			f = f.strip("\r\n\x00",)

			uri = vfs_clean_uri(f)
			lines = None
			try:
				content = gnomevfs.read_entire_file(uri)
			except gnomevfs.IsDirectoryError:
				pass
			except gnomevfs.NotFoundError:
				pass
			else:
				lines = content.split("\n")
				if lines and self.get_hashfile_format(uri, lines):
						glade = os.path.join(DATADIR, "parano.glade")
						dialog = gtk.glade.XML(glade,"dialog_add_or_open")
						dialog = dialog.get_widget("dialog_add_or_open")
				
						result = dialog.run()
						dialog.hide_all()
						if result == gtk.RESPONSE_CANCEL:
							# abort drop
							return
						if result == gtk.RESPONSE_CLOSE:
							# open new hashfile
							self.load_hashfile(f)
							return
			
			# add the file or folder
			self.add_file(f)
		
		self.modified=True
		self.update_ui()

	def __init__(self, initial_files=[]):
		self.init_window()		
		self.new_hashfile()

		debug("datadir:", DATADIR)

		if len(initial_files) == 1:
			# load hash file
			log("One file specified, trying to load as HashFile.")
			filename = initial_files[0]
			#if self.get_hashfile_format(filename):
			#	log("HashFile detected, loading.")
			self.load_hashfile(filename)
			initial_files=[]
		
		for f in initial_files:
			log("Adding file: "+f)
			self.add_file(f)
			
		self.update_title()
		self.modified=False
		self.update_file_list()

	def main(self):
		gtk.main()
	
def excepthook(type, value, tb):
	trace = cStringIO.StringIO()
	traceback.print_exception(type, value, tb, None, trace)
	print trace.getvalue()
	message = _(
	"<big><b>A programming error has been detected during the execution of %s %s.</b></big>"
	"\n\n<tt><small>%s</small></tt>") % ( NAME, VERSION, trace.getvalue())
	dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, 
		gtk.BUTTONS_OK, message)
	dialog.set_title(_("Bug Detected"))
	dialog.set_markup(message)
	dialog.run()
	dialog.hide()
	sys.exit(1)

if __name__ == "__main__":

	sys.excepthook = excepthook

	name = "parano"
	gettext.install(name, unicode=1)
	gtk.glade.bindtextdomain(name)
	gtk.glade.textdomain(name)

	# (longName, shortName, type , default, flags, descrip , argDescrip)
	table=[
		("quiet"  , 'q'   , None ,   None  , 0    , 'Do not print any message on stdout'   , ""),
	]

	gnome.init(NAME, VERSION, gnome.libgnome_module_info_get()) 
	
	leftover, argdict = gnome.popt_parse(sys.argv, table)

	if argdict["quiet"]: option_quiet = True
		
	log(NAME +" "+ VERSION)
	debug("datadir: "+DATADIR)

	parano = Parano(leftover)
	parano.main()
