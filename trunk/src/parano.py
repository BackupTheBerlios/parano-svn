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

import os, sys , time, string, re
import thread
import md5, zlib
import pygtk
pygtk.require('2.0')
import gobject, gtk, gtk.glade, gnome, gnome.ui
import cStringIO, traceback
import urllib
import gettext
_=gettext.gettext

def gtk_iteration():
	while gtk.events_pending():
		gtk.main_iteration(False)

def auto_connect(object, dialog):
	for w in dialog.get_widget_prefix(''):
		name = w.get_name()
		assert not hasattr(object, name), name
		setattr(object, name, w)

option_quiet = False

def log(*args):
	if not option_quiet:
		ss = " ".join(args)
		print ss
		
		f = file("parano.log","a")
		f.write(ss+"\n")
		f.close()

def debug(str):
	print str

COLUMN_ICON=0
COLUMN_FILE=1

BUFFER_SIZE=1024*64

HASH_NOT_CHECKED=0	# hash not checked yet
HASH_OK=1			# hash is as excepted
HASH_ERROR=2		# cannot check hash
HASH_DIFFERENT=3 	# hash is not what expected: file corrupted !
HASH_MISSING=4		# file is missing

icons = {
	HASH_NOT_CHECKED	:  None,
	HASH_OK			: gtk.STOCK_YES,
	HASH_ERROR		: gtk.STOCK_DIALOG_ERROR,
	HASH_DIFFERENT	: gtk.STOCK_NO,
	HASH_MISSING	: gtk.STOCK_MISSING_IMAGE	
}

class File:
	# File contained in hash file
	def __init__(self, filename="", displayed_name="", expected_hash="", size=0):
		if displayed_name:
			self.displayed_name=displayed_name
		else:
			self.displayed_name=filename
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
				self.size = os.path.getsize(self.filename)
			except OSError:
				log(_("Warning: cannot get size of file '%s'") % filename)
				self.size = 0;

class HasherMD5:
	def init(self):
		self.hasher = md5.new()
		
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

		self.regex_reader = re.compile(r";.*|#.*|^(?P<hash>[\dA-Fa-f]{32}) \*?(?P<file>.*$)|^\s*$")
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

formats = (FormatMD5(), FormatSFV())

class Parano:

	def get_file_hash(self, filename):
		# compute hash of given file	
		try:
			f = open(filename, 'rb');
		except IOError:
			log( _("Cannot read file: "), filename)
			return ""
		
		hasher = self.format.hasher
		hasher.init()
		
		while 1:
			while self.paused:
				# paused, wait forever
				gtk_iteration()
				time.sleep(0.1)
				
			data = f.read(BUFFER_SIZE)
			if not data:
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

	def get_hashfile_format(self, filename):
	
		try:
			f = open(filename, "r")
	
			for format in formats:
				# search in al our recognized formats
				regex = format.filename_regex
				result = regex.search(filename.lower())
				if result:
					# this can be a valid filename, now look inside
					f.seek(0)
					if format.detect_file(f):
						# yes, this is a valid hashfile \o/
						f.close()
						return format
					
			f.close()
		except IOError:
			pass
			
		return None

	def load_hashfile(self, filename):
		# load hashfile

		files_to_add=[]
		self.format=self.get_hashfile_format(filename)
				
		if not self.format:
			log("unknown format")
			f.close()
			return
		log("Detected format: " + self.format.name)
				
		f = open(filename, "r")
		list = self.format.read_file(f)
		f.close()
	
		for hash, file in list:
			root = os.path.dirname(filename)
			absfile = os.path.join(root, file)
			files_to_add.append( (absfile, file, hash) )
		
		# reset hashfile
		self.new_hashfile()
		
		# do add the files to list
		for f in files_to_add:
			self.files.append(File(f[0], f[1], f[2]))
		
		self.filename=filename
		self.update_ui()
		self.update_hashfile()

	def save_hashfile(self, filename):

		for format in formats:
			regex = format.filename_regex
			result = regex.search(filename)
			if result:
				self.format = format
				log("Saving with format:", format.name)
				break

		self.update_hashfile()

		list=[]
		remove = len(os.path.dirname(filename))+1
		for ff in self.files:
			# convert to a path relative to hashfile
			if len(ff.filename)<remove:
				# TODO: better error detection
				dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, 
							_("Cannot store a md5 file in the hashed tree"))
				dialog.run()
				dialog.hide_all()
				return
			file = ff.filename[remove:]
			hash = ff.real_hash
			list.append( (hash,file) )
			
		
		f = open(filename, "w")
		self.format.write_file(f, list)
		f.close()
		
		self.modified=False
		self.filename=filename
		self.update_title()

	def add_file(self, filename, displayed_name="", hash=""):
		if os.path.isfile(filename):
			self.files.append(File(filename, displayed_name, hash))
		elif os.path.isdir(filename):
			self.add_folder(filename)
		else:
			log("error when tring to add: '%s'" % filename)

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
		label_filename = self.progress_dialog.get_widget("label_filename")
		progressbar = self.progress_dialog.get_widget("progressbar")
		if self.paused:
			label_filename.set_markup(_("<i>%s (Paused)</i>") % self.current_file)
			progressbar.set_text(_("Paused"))
		else:
			label_filename.set_markup("<i>%s</i>" % self.current_file)


	def thread_update_hash(self):
	
		for f in self.files:
			if self.abort:
				# cancel button pressed
				break

			#if f.status == HASH_NOT_CHECKED:
			# for progress
			self.current_file = os.path.basename(f.filename)
			
			f.real_hash = self.get_file_hash(f.filename)
			self.progress_file=self.progress_file+1
			
			if len(f.expected_hash) == 0:
				# new file in md5
				f.status = HASH_OK
			else:	
				print self.current_file, f.real_hash, f.expected_hash
				if f.real_hash.lower() == f.expected_hash.lower():
					# matching md5
					f.status = HASH_OK
				else:
					if len(f.real_hash) == 0:
						if os.path.exists(self.current_file):
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
		glade = os.path.join(DATADIR, "parano.glade")
		self.progress_dialog = dialog = gtk.glade.XML(glade,"hashing_progress")
		progress = self.progress_dialog_dlg = dialog.get_widget("hashing_progress")
		self.window_main.set_sensitive(False)
		progress.set_transient_for(self.window_main)

		events = { 
					"on_button_cancel_clicked" : self.on_update_hash_cancel,
					"on_button_pause_clicked" : self.on_update_hash_pause 
		}
		dialog.signal_autoconnect(events)
		progressbar = dialog.get_widget("progressbar")
		progresslabel = dialog.get_widget("label_filename")
		progressfiles = dialog.get_widget("label_files")

		progresslabel.set_markup("")
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
			if not self.paused:
				now=time.time()
				progresslabel.set_markup("<i>%s</i>" % self.current_file)
				fraction = float(self.progress_current_bytes)/float(self.progress_total_bytes)
				
				if fraction>1.0:
					fraction=1.0
				progressbar.set_fraction(fraction)
				if fraction>0.0:
					remaining = int((now-start)/fraction-(now-start))
					minutes = remaining/60
					seconds = remaining%60
					text = _("(%d:%02d Remaining)") % (minutes, seconds)
					progressbar.set_text(text)
					text = _("<b>%d / %d</b>") % (self.progress_file, self.progress_nbfiles)
					progressfiles.set_markup(text)
				
			gtk_iteration()
			time.sleep(0.1)

		log( "%.2f MiB/s" % (total/(time.time()-start)/(1024*1024)))

		self.update_and_check_file_list()  
		progress.hide_all()	
		self.window_main.set_sensitive(True)

	def update_file_list(self):  
		self.liststore.clear()
		changed, missing, error = 0,0,0
		for f in self.files:
			iter = self.liststore.append()
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
			self.statusbar.push(_("Warning: %d files are different!") % (changed+missing+error))
			dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, 
				gtk.BUTTONS_OK, "")
			dialog.set_title(_("File Corruption Detected"))
			dialog.set_markup(_("<b>Integrity alert!</b>\n\n"
				"Warning! <b>%d</b> files are different, details follows:\n" 
				"  modified: <b>%d</b>\n"
				"  missing: <b>%d</b>\n"
				"  reading errors: <b>%d</b>\n"
				"") % ( changed+missing+error, changed, missing, error))
			dialog.run()
			dialog.hide()
			
		else:
			if self.files:
				self.statusbar.push(_("%d files verified and ok.") % len(self.files))
			else:	
				self.statusbar.push(_("Ready."))
		

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
		if result == gtk.RESPONSE_OK:
			self.load_hashfile(dialog.get_filename())
	
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
		if result == gtk.RESPONSE_OK:
			self.filename = dialog.get_filename()
			
			if os.path.exists(self.filename):
				glade = os.path.join(DATADIR, "parano.glade")
				dialog_ow = gtk.glade.XML(glade,"dialog_overwrite_file")\
							.get_widget("dialog_overwrite_file")
				result = dialog_ow.run()
				dialog_ow.hide_all()
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
			for f in dialog.get_filenames():
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
			self.add_folder(dialog.get_filename())
			
		gtk_iteration()

	def add_folder(self, folder):
		glade = os.path.join(DATADIR, "parano.glade")
		self.progress_dialog = gtk.glade.XML(glade,"addfolder_progress")
		
		events = { "on_button_cancel_clicked" : self.on_addfolder_cancel }
		self.progress_dialog.signal_autoconnect(events)
		
		progress = self.progress_dialog.get_widget("addfolder_progress")

		progressbar = self.progress_dialog.get_widget("progressbar")
		progresslabel = self.progress_dialog.get_widget("label_folder")

		progress.set_transient_for(self.window_main)
		
		self.abort=False
		progress.show()	
		gtk_iteration()
		time.sleep(0.1)
		
		# save current files list
		backup = self.files[:]
		t=0
		for root, dirs, files in os.walk(folder):
			if time.time()-t >= 0.1:
				t = time.time()
				progresslabel.set_markup("<small><i>%s</i></small>" % root)
				progressbar.pulse()
			gtk_iteration()
			for name in files:
				f = os.path.join(root, name)
				self.add_file(f)
				if self.abort:
					break
			if self.abort:
				break
	
		if not self.abort:
			self.modified=True
			self.update_ui()

		if self.abort:
			# restore original file list
			self.files = backup
		progress.hide_all()	

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
		window = gtk.glade.XML(glade,"window_main")
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
		
			f = urllib.unquote(f)
			# remove "file://"	
			result = re.search(r"file:(//)?(.*)", f)
			if result:
				f = result.group(2)
				
			# remove trailing noise
			f = f.strip("\r\n\x00",)
						
			if self.get_hashfile_format(f):
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
			
			# add the file
			if os.path.exists(f):
				self.add_file(f)
			elif f: # TODO: error
				log( _("skipping dropped uri: %s") % repr(f))
		
		self.modified=True
		self.update_ui()

	def __init__(self, initial_files=[]):
		self.init_window()		
		self.new_hashfile()

		if len(initial_files) == 1:
			# load hash file
			log("One file specified, trying to load as HashFile.")
			filename = initial_files[0]
			if self.get_hashfile_format(filename):
				log("HashFile detected, loading.")
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
	"<big><b>A programming error has been detected during the execution of this program.</b></big>"
	"\n\n<tt><small>%s</small></tt>") % trace.getvalue()
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
	log("datadir: "+DATADIR)

	parano = Parano(leftover)
	parano.main()
