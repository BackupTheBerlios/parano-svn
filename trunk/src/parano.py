#!/usr/bin/env python

# Parano - GNOME MD5 Frontend
# Copyright (C) 2004 Gautier Portet <kassoulet@gmail.com>

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
    
import os
import sys
import pdb
import time
import string
import re
import thread
import md5
import pygtk
pygtk.require('2.0')
import gobject
import gtk
import gtk.glade
import gnome
import gettext
_=gettext.gettext

COLUMN_ICON=0
COLUMN_HASH=1
COLUMN_FILE=2

BUFFER_SIZE=1024

MD5_NOT_CHECKED=0	# md5 not checked yet
MD5_OK=1			# md5 is as excepted
MD5_ERROR=2			# cannot check md5
MD5_DIFFERENT=3 	# md5 is not what expected: file corrupted !

icons = {
	MD5_NOT_CHECKED	: gtk.STOCK_MISSING_IMAGE,
	MD5_OK			: gtk.STOCK_YES,
	MD5_ERROR		: gtk.STOCK_DIALOG_WARNING,
	MD5_DIFFERENT	: gtk.STOCK_NO,
}
class File:
	# File contained in MD5 collection 
	def __init__(self, filename="", expectedMD5="", size=-1):
		# the filename
		self.filename=filename
		# the MD5 loaded from file
		self.expectedMD5=expectedMD5
		# the MD5 calculated
		self.realMD5=""
		# the file size
		self.size=size
		# sum status
		self.status=MD5_NOT_CHECKED

def gtk_iteration():
	while gtk.events_pending():
		gtk.main_iteration(gtk.FALSE)

class Parano:

	def calculate_file_md5(self, filename):
		# compute MD5 hash of given file	
		try:
			f = open(filename, 'rb');
		except IOError:
			print "HASHING ERROR", filename
			return ""
		
		hasher = md5.new()

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

		return hasher.hexdigest()

	def new_md5(self):
		# reset MD5
		self.filename=""
		self.files=[]
		self.total_size=0
		self.liststore.clear()
		self.modified=False
		self.update_title()

	def load_md5(self, filename):
		# load MD5 from file

		f = open(filename, "r")

		files_to_add=[]
		line="\n"	
		while line != "":
			line = f.readline()
			
			valid=True
			if line=="":
				# EOF
				valid=False
			if line.find(";")!=-1:
				# comment
				valid=False
			
			if valid:
				# 32
				if len(line)<=35:
					# line too shot !
					valid=False
	
				if valid:
					md5 = line[:32]
					file= line[34:-1]
					for c in md5:
						if c not in string.hexdigits:
							# not a valid md5 sum
							valid=False
					for c in file:
						if c < 32:
							# cannot be a filename
							valid=False

				if not valid:
					# fatal error! stop loading
					dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, 
								_("Cannot read %s\nIt's maybe not a MD5 sum file")%filename)
					dialog.run()
					dialog.hide_all()
					f.close()
					return
					
				if file[0] == "*":
					# remove binary flag if present
					file = file[1:]

				# convert filename from relative to md5 file to absolute
				root = os.path.dirname(filename)
				absfile = os.path.join(root, file)

				files_to_add.append(File(absfile, md5))
			
		f.close()
		
		self.new_md5()
		
		for f in files_to_add:
			self.add_file(f.filename, f.expectedMD5)
		
		self.filename=filename
		self.modified=False
		self.update_title()
		self.update_file_list()
		self.update_md5()
				
	def save_md5(self, filename):
	
		f = open(filename, "w")
		remove = len(os.path.dirname(filename))+1
		for ff in self.files:
			# convert to a path relative to md5 file
			filename = ff.filename[remove:]
			f.write("%s *%s\n" % (ff.realMD5,filename))
		f.close()
		self.modified=False
		self.filename=filename
		self.update_title()

	def add_file(self, filename, md5=""):
	
		try:
			size = os.path.getsize(filename)
		except OSError:
			print _("Warning: cannot get size of file '%s'") % filename
			size = 0;
		f = File(filename,md5,size)
		self.files.append(f)

	def update_title(self):
		
		if self.filename != "":
			title = os.path.basename(self.filename)
		else:
			title = _("Untitled MD5")
		if self.modified:
			title = _("%s (Unsaved)") % title
			
		self.window_main.set_title(title)

	def on_update_md5_cancel(self, widget):
		self.paused = False
		self.abort = True	

	def on_update_md5_pause(self, widget):
		self.paused = not self.paused
		if self.paused:
			self.progress_dialog.get_widget("label_filename").set_markup(_("<i>%s (Paused)</i>") % self.current_file)
			self.progress_dialog.get_widget("progressbar").set_text(_("Paused"))
		else:
			self.progress_dialog.get_widget("label_filename").set_markup("<i>%s</i>" % self.current_file)


	def thread_update_md5(self):
	
		for f in self.files:
			if self.abort:
				# cancel button pressed
				break

			if f.status == MD5_NOT_CHECKED:
					
				# for progress
				self.current_file = os.path.basename(f.filename)
				
				f.realMD5 = self.calculate_file_md5(f.filename)
				self.progress_file=self.progress_file+1
				
				if len(f.expectedMD5) == 0:
					# new file in md5
					f.status = MD5_OK
				else:	
					if f.realMD5 == f.expectedMD5:
						# matching md5
						f.status = MD5_OK
					else:
						if len(f.realMD5) == 0:
							# cannot read file
							f.status = MD5_ERROR
						else:
							# md5 mismatch
							f.status = MD5_DIFFERENT

		# stop progress
		self.progress_total_bytes=0


	def update_md5(self):

		self.progress_dialog = gtk.glade.XML("parano.glade","hashing_progress")
		progress = self.progress_dialog_dlg = self.progress_dialog.get_widget("hashing_progress")

		events = { 
					"on_button_cancel_clicked" : self.on_update_md5_cancel,
					"on_button_pause_clicked" : self.on_update_md5_pause 
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
		thread.start_new_thread(self.thread_update_md5, ())
		
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
		
		self.update_file_list()  
		progress.hide_all()	

	def update_file_list(self):  
		self.liststore.clear()
		for f in self.files:
			iter = self.liststore.append()
			self.liststore.set(iter, COLUMN_FILE, f.filename, COLUMN_HASH, f.realMD5)
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

	def on_new_md5_activate(self, widget):
		# new_md5
		self.new_md5()

	def on_load_md5_activate(self, widget):
		# load_md5 dialog
		self.loadmd5_dialog = gtk.glade.XML("parano.glade","filechooserdialog_loadmd5")
		dialog = self.loadmd5_dialog.get_widget("filechooserdialog_loadmd5")
		result = dialog.run()
		if result == gtk.RESPONSE_OK:
			self.load_md5(dialog.get_filename())
	
		self.update_file_list()
		dialog.hide_all()
		
	def on_save_md5_activate(self, widget):
		# save_md5 dialog
		if self.filename != "":
			self.save_md5(self.filename)
		else:
			self.on_save_as_md5_activate(widget)

	def on_save_as_md5_activate(self, widget):
		# save_as_md5 dialog
		self.savemd5_dialog = gtk.glade.XML("parano.glade","filechooserdialog_savemd5")
		dialog = self.savemd5_dialog.get_widget("filechooserdialog_savemd5")
		result = dialog.run()
		if result == gtk.RESPONSE_OK:
			self.filename = dialog.get_filename()
			
			if os.path.exists(self.filename):
				dialog = gtk.glade.XML("parano.glade","dialog_overwrite_file")\
							.get_widget("dialog_overwrite_file")
				result = dialog.run()
				dialog.hide_all()
				if result == gtk.RESPONSE_CANCEL:
					# cancel
					return
	
			self.save_md5(self.filename)
	
		dialog.hide_all()

	def on_addfile_activate(self, widget):
		# addfile dialog
		self.addfile_dialog = gtk.glade.XML("parano.glade","filechooserdialog_addfile")
			
		dialog = self.addfile_dialog_dlg = self.addfile_dialog.get_widget("filechooserdialog_addfile")
		result = dialog.run()
		if result == gtk.RESPONSE_OK:
			for f in dialog.get_filenames():
				self.add_file(f)
	
		self.update_md5()
	
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
					self.add_file(os.path.join(root, name))
					if self.abort:
						break
				if self.abort:
					break
		
		
		progress.hide_all()	
					
		if not self.abort:
			self.update_md5()
	
		gtk_iteration()
		if not self.abort:
			self.update_file_list()
			self.modified=True
			self.update_title()

		if self.abort:
			# restore original file list
			self.files = backup


	def on_addfolder_cancel(self, widget):
		self.abort=True	
			
	def on_refresh(self, widget):
		for f in self.files:
			f.status = MD5_NOT_CHECKED
		self.update_md5()

	def init_window(self):
		# main window
		self.window_main_xml = gtk.glade.XML("parano.glade","window_parano")
		events = { 
				"on_about_activate" : self.on_about_activate,
				"on_addfile_activate" : self.on_addfile_activate,
				"on_addfolder_activate" : self.on_addfolder_activate,
				"on_new_md5_activate" : self.on_new_md5_activate,
				"on_load_md5_activate" : self.on_load_md5_activate,
				"on_save_md5_activate" : self.on_save_md5_activate,
				"on_save_as_md5_activate" : self.on_save_as_md5_activate,
				"on_refresh" : self.on_refresh,
				"on_quit_activate" : self.on_quit_activate,
				"on_destroy" : self.on_destroy,
				"on_delete_event" : self.on_event_delete 
				}
		self.window_main_xml.signal_autoconnect(events)

		self.window_main = self.window_main_xml.get_widget("window_parano")

		filelist = self.window_main_xml.get_widget("filelist")
		
		renderer = gtk.CellRendererPixbuf()
		renderer.set_property("stock-id", gtk.STOCK_MISSING_IMAGE)
		column = gtk.TreeViewColumn("Status", renderer)
		column.set_sort_column_id(COLUMN_ICON)
		column.add_attribute(renderer, "stock_id", COLUMN_ICON)
		
		filelist.append_column(column)
		column = gtk.TreeViewColumn("Hash", gtk.CellRendererText(),
		                            text=COLUMN_HASH)
		column.set_sort_column_id(COLUMN_HASH)
		
		#renderer = gtk.CellRendererText()
		#column.pack_start(renderer, gtk.TRUE)
		#column.add_attribute(renderer, "text", COLUMN_HASH)
	
		filelist.append_column(column)
		
		column = gtk.TreeViewColumn("File", gtk.CellRendererText(),
		                            text=COLUMN_FILE)
		column.set_sort_column_id(COLUMN_FILE)
		filelist.append_column(column)

		self.liststore = gtk.ListStore(gobject.TYPE_STRING,gobject.TYPE_STRING,gobject.TYPE_STRING)
		filelist.set_model(self.liststore)
	

	def __init__(self, initial_files=""):
		self.init_window()		
		self.new_md5()

		number_md5=0

		for f in initial_files:
			lower = string.lower(f)
			if string.rfind(lower,".md5") != -1:
				print "loading md5:", f
				self.load_md5(f)
				number_md5=number_md5+1
			else:
				self.add_file(f)
				
		if number_md5>1:
			self.filename=""
			
		self.update_title()
		self.modified=False
		self.update_file_list()
		if number_md5>0:
			self.update_md5()

								
	def main(self):
		gtk.main()

if __name__ == "__main__":

	# (longName, shortName, type , default, flags, descrip , argDescrip)
	table=[]

	gnome.init("Parano", "0.1", gnome.libgnome_module_info_get()) 
	
	leftover, argdict = gnome.popt_parse(sys.argv, table)
	
	parano = Parano(leftover)
	parano.main()
