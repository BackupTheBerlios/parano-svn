#!/usr/bin/env python

# Parano - GNOME HashFile Frontend
# Copyright (C) 2004-2005 Gautier Portet <kassoulet@gmail.com>

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

PACKAGE="Parano"
VERSION="0.2"
URL="http://parano.berlios.de"

import os
import sys
import pdb
import time
import string
import re
import thread
import md5
import zlib
import pygtk
pygtk.require('2.0')
import gobject
import gtk
import gtk.glade
import gnome
import gettext
_=gettext.gettext

COLUMN_ICON=0
#COLUMN_HASH=1
COLUMN_FILE=1

BUFFER_SIZE=1024*64

HASH_NOT_CHECKED=0	# hash not checked yet
HASH_OK=1			# hash is as excepted
HASH_ERROR=2			# cannot check hash
HASH_DIFFERENT=3 	# hash is not what expected: file corrupted !

icons = {
	HASH_NOT_CHECKED	: None,
	HASH_OK			: gtk.STOCK_YES,
	HASH_ERROR		: gtk.STOCK_DIALOG_WARNING,
	HASH_DIFFERENT	: gtk.STOCK_NO,
}
class File:
	# File contained in hash file
	def __init__(self, displayed_name="", filename="", expected_hash="", size=0):
		# the displayed name
		self.displayed_name=displayed_name
		# the filename
		self.filename=filename
		# the Hash loaded from file
		self.expected_hash=expected_hash
		# the Hash calculated
		self.real_hash=""
		# the file size
		self.size=size
		# sum status
		self.status=HASH_NOT_CHECKED

		if not size:
			try:
				self.size = os.path.getsize(self.filename)
			except OSError:
				print _("Warning: cannot get size of file '%s'") % filename
				self.size = 0;


def gtk_iteration():
	while gtk.events_pending():
		gtk.main_iteration(gtk.FALSE)

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
		return "%8X" % self.crc

class FormatBase:
	def detect_file(self, f):
		for line in f:
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
		comment = "Created by %s %s - %s" % (PACKAGE, VERSION, URL)
		f.write(self.format_comment % comment)
		for hash, file in list:
			f.write(self.format_writer % locals())

class FormatMD5 (FormatBase):
	def __init__(self):
		self.name = "MD5"
		self.filename_pattern = "*.md5*"
		self.filename_regex = re.compile(r".*\.md5(sum)?")
		self.hasher = HasherMD5()

		self.regex_reader = re.compile(r";.*|^(?P<hash>[\dA-Fa-f]{32}) \*?(?P<file>.*$)|^\s*$")
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
			print "HASHING ERROR", filename
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

	def load_hashfile(self, filename):
		# load hashfile

		f = open(filename, "r")

		files_to_add=[]
		self.format=None
		for format in formats:
			f.seek(0)
			if format.detect_file(f):
				self.format = format
				print "Detected format:", format.name
				
		if not self.format:
			print "unknown format"
			f.close()
			return
				
		f.seek(0)
		list = self.format.read_file(f)
		f.close()
	
		for hash, file in list:
			root = os.path.dirname(filename)
			absfile = os.path.join(root, file)
			files_to_add.append(File(file, absfile, hash))
		
		# reset hashfile
		self.new_hashfile()
		
		# do add the files to list
		for f in files_to_add:
			self.add_file(f)
		
		self.filename=filename
		self.update_ui()
		self.update_hashfile()

	def save_hashfile(self, filename):

		for format in formats:
			regex = format.filename_regex
			result = regex.search(filename)
			if result:
				self.format = format
				print "Saving with format:", format.name
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

	def add_file(self, f):
		self.files.append(f)

	def update_ui(self):
		self.update_title()
		self.update_file_list()

	def update_title(self):
		
		if self.filename != "":
			title = os.path.basename(self.filename)
		else:
			title = _("Untitled MD5")
		if self.modified:
			title = _("%s (Unsaved)") % title
			
		self.window_main.set_title(title)

	def on_update_hash_cancel(self, widget):
		self.paused = False
		self.abort = True	

	def on_update_hash_pause(self, widget):
		self.paused = not self.paused
		if self.paused:
			self.progress_dialog.get_widget("label_filename").set_markup(_("<i>%s (Paused)</i>") % self.current_file)
			self.progress_dialog.get_widget("progressbar").set_text(_("Paused"))
		else:
			self.progress_dialog.get_widget("label_filename").set_markup("<i>%s</i>" % self.current_file)


	def thread_update_hash(self):
	
		for f in self.files:
			if self.abort:
				# cancel button pressed
				break

			if f.status == HASH_NOT_CHECKED:
					
				# for progress
				self.current_file = os.path.basename(f.filename)
				
				f.real_hash = self.get_file_hash(f.filename)
				self.progress_file=self.progress_file+1
				
				if len(f.expected_hash) == 0:
					# new file in md5
					f.status = HASH_OK
				else:	
					if f.real_hash == f.expected_hash:
						# matching md5
						f.status = HASH_OK
					else:
						if len(f.real_hash) == 0:
							# cannot read file
							f.status = HASH_ERROR
						else:
							# md5 mismatch
							f.status = HASH_DIFFERENT

		# stop progress
		self.progress_total_bytes=0


	def update_hashfile(self):

		self.progress_dialog = gtk.glade.XML("parano.glade","hashing_progress")
		progress = self.progress_dialog_dlg = self.progress_dialog.get_widget("hashing_progress")

		events = { 
					"on_button_cancel_clicked" : self.on_update_hash_cancel,
					"on_button_pause_clicked" : self.on_update_hash_pause 
				}
		self.progress_dialog.signal_autoconnect(events)
		progressbar = self.progress_dialog.get_widget("progressbar")
		progresslabel = self.progress_dialog.get_widget("label_filename")
		progressfiles = self.progress_dialog.get_widget("label_files")

		progresslabel.set_markup("")
		progress.show()	

		gtk_iteration()

		self.abort = False
		self.paused = False
		
		self.progress_nbfiles=len(self.files)
		self.progress_file=0
		self.current_file=""

		self.progress_total_bytes=666
		for f in self.files:
			self.progress_total_bytes=self.progress_total_bytes+f.size
		self.progress_current_bytes=0

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

		print (total/(time.time()-start))/(1024*1024), "MB/s"

		self.update_file_list()  
		progress.hide_all()	

	def update_file_list(self):  
		self.liststore.clear()
		for f in self.files:
			iter = self.liststore.append()
			self.liststore.set(iter, COLUMN_FILE, f.displayed_name)
			self.liststore.set(iter, COLUMN_ICON, icons[f.status])


	def on_quit_activate(self, widget):
		if not self.on_event_delete(widget):
			gtk.main_quit()

	def on_event_delete(self, widget, event=None, data=None):
		# Change FALSE to TRUE and the main window will not be destroyed
		# with a "delete_event".
		if self.modified:
			dialog = gtk.glade.XML("parano.glade","dialog_save_before_closing")\
						.get_widget("dialog_save_before_closing")
			result = dialog.run()
			dialog.hide_all()
			if result == gtk.RESPONSE_OK:
				# save
				self.on_save_md5_activate(widget)
				return gtk.TRUE
			if result == gtk.RESPONSE_CANCEL:
				# cancel
				return gtk.TRUE
			if result == gtk.RESPONSE_CLOSE:
				# close
				return gtk.FALSE

		return gtk.FALSE

	def on_destroy(self, widget, data=None):
		gtk.main_quit()
		
	def on_about_activate(self, widget):
		# about dialog
		self.about_dialog = gtk.glade.XML("parano.glade","dialog_about")

	def on_new_hashfile_activate(self, widget):
		# new_hashfile
		self.new_hashfile()

	def on_load_hashfile_activate(self, widget):
		# load_hashfile dialog
		self.loadhashfile_dialog = gtk.glade.XML("parano.glade","filechooserdialog_loadhashfile")
		dialog = self.loadhashfile_dialog.get_widget("filechooserdialog_loadhashfile")

		filter = gtk.FileFilter()
		
		for format in formats:
			filter.add_pattern(format.filename_pattern)

		dialog.set_filter(filter)

		#hash = gtk.CheckButton(_("Calculate hash automatically"))
		#hash.show ()
		#self.addfolder_dialog.get_widget("filechooserdialog_addfolder").set_extra_widget(hash)

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
		self.savehashfile_dialog = gtk.glade.XML("parano.glade","filechooserdialog_savehashfile")
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
				dialog_ow = gtk.glade.XML("parano.glade","dialog_overwrite_file")\
							.get_widget("dialog_overwrite_file")
				result = dialog_ow.run()
				dialog_ow.hide_all()
				if result == gtk.RESPONSE_CANCEL:
					# cancel
					return
			self.save_hashfile(self.filename)
	

	def on_addfile_activate(self, widget):
		# addfile dialog
		self.addfile_dialog = gtk.glade.XML("parano.glade","filechooserdialog_addfile")
			
		dialog = self.addfile_dialog_dlg = self.addfile_dialog.get_widget("filechooserdialog_addfile")
		result = dialog.run()
		if result == gtk.RESPONSE_OK:
			for f in dialog.get_filenames():
				self.add_file(File(f,f))
	
		#self.update_md5()
	
		self.update_file_list()
		dialog.hide_all()
		self.modified=True
		self.update_title()
		
	def on_addfolder_activate(self, widget):
		# addfolder dialog
		self.addfolder_dialog = gtk.glade.XML("parano.glade","filechooserdialog_addfolder")

		dialog = self.addfolder_dialog_dlg = self.addfolder_dialog.get_widget("filechooserdialog_addfolder")

		hash = gtk.CheckButton(_("Calculate hash automatically"))
		hash.show ()
		self.addfolder_dialog.get_widget("filechooserdialog_addfolder").set_extra_widget(hash)
		
		result = dialog.run()
		
		dialog.hide_all()
		
		gtk_iteration()
		
		self.progress_dialog = gtk.glade.XML("parano.glade","addfolder_progress")
		
		events = { "on_button_cancel_clicked" : self.on_addfolder_cancel }
		self.progress_dialog.signal_autoconnect(events)
		
		progress = self.progress_dialog.get_widget("addfolder_progress")

		progressbar = self.progress_dialog.get_widget("progressbar")
		progresslabel = self.progress_dialog.get_widget("label_folder")

		self.abort=False
		progress.show()	
		gtk_iteration()
		time.sleep(0.1)
		
		# save current files list
		backup = self.files[:]
		
		t=0
		if result == gtk.RESPONSE_OK:
			for root, dirs, files in os.walk(dialog.get_filename()):
				if time.time()-t >= 0.1:
					t = time.time()
					progresslabel.set_markup("<small><i>%s</i></small>" % root)
					progressbar.pulse()
				gtk_iteration()
				for name in files:
					f = os.path.join(root, name)
					self.add_file(File(f,f))
					if self.abort:
						break
				if self.abort:
					break
		
		
		progress.hide_all()	
					
		#if not self.abort:
			#self.update_md5()
	
		gtk_iteration()
		if not self.abort:
			self.modified=True
			self.update_ui()

		if self.abort:
			# restore original file list
			self.files = backup

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
		self.window_main_xml = gtk.glade.XML("parano.glade","window_parano")
		events = { 
				"on_about_activate" : self.on_about_activate,
				"on_addfile_activate" : self.on_addfile_activate,
				"on_addfolder_activate" : self.on_addfolder_activate,
				"on_remove_activate" : self.on_remove_activate,
				"on_new_hashfile_activate" : self.on_new_hashfile_activate,
				"on_load_hashfile_activate" : self.on_load_hashfile_activate,
				"on_save_hashfile_activate" : self.on_save_hashfile_activate,
				"on_save_as_hashfile_activate" : self.on_save_as_hashfile_activate,
				"on_refresh" : self.on_refresh,
				"on_quit_activate" : self.on_quit_activate,
				"on_destroy" : self.on_destroy,
				"on_delete_event" : self.on_event_delete 
				}
		self.window_main_xml.signal_autoconnect(events)

		self.window_main = self.window_main_xml.get_widget("window_parano")

		self.filelist = filelist = self.window_main_xml.get_widget("filelist")
		filelist.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
		
		renderer = gtk.CellRendererPixbuf()
		renderer.set_property("stock-id", gtk.STOCK_MISSING_IMAGE)
		column = gtk.TreeViewColumn("Status", renderer)
		column.set_sort_column_id(COLUMN_ICON)
		column.add_attribute(renderer, "stock_id", COLUMN_ICON)
		
		#filelist.append_column(column)
		#column = gtk.TreeViewColumn("Hash", gtk.CellRendererText(),
		#                            text=COLUMN_HASH)
		#column.set_sort_column_id(COLUMN_HASH)
		
		#renderer = gtk.CellRendererText()
		#column.pack_start(renderer, gtk.TRUE)
		#column.add_attribute(renderer, "text", COLUMN_HASH)
	
		filelist.append_column(column)
		
		column = gtk.TreeViewColumn("File", gtk.CellRendererText(),
		                            text=COLUMN_FILE)
		column.set_sort_column_id(COLUMN_FILE)
		filelist.append_column(column)

		self.liststore = gtk.ListStore(gobject.TYPE_STRING,gobject.TYPE_STRING)
		filelist.set_model(self.liststore)
	

	def __init__(self, initial_files=""):
		self.init_window()		
		self.new_hashfile()

		number_hashfile=0

		for f in initial_files:
			lower = string.lower(f)
			# TODO: fix this
			if string.rfind(lower,".md5") != -1:
				print "loading md5:", f
				self.load_hashfile(f)
				number_hashfile=number_hashfile+1
			else:
				self.add_file(f)
				
		if number_hashfile>1:
			self.filename=""
			
		self.update_title()
		self.modified=False
		self.update_file_list()
		if number_hashfile>0:
			self.update_hashfile()

								
	def main(self):
		gtk.main()

if __name__ == "__main__":

	# (longName, shortName, type , default, flags, descrip , argDescrip)
	table=[]

	gnome.init("Parano", "0.1", gnome.libgnome_module_info_get()) 
	
	leftover, argdict = gnome.popt_parse(sys.argv, table)
	
	parano = Parano(leftover)
	parano.main()
