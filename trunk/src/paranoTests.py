#!/usr/bin/python
# -*- coding: utf-8 -*-
# (c) 2006 Gautier Portet <kassoulet gmail com>

import unittest
import parano
parano.option_quiet = True
import os
import glob
import gnome
import gnomevfs
import gtk
from random import randint

gnome.init("Parano Test", "wip", gnome.libgnome_module_info_get()) 
parano.DATADIR="src"

base_folder = "test/"
test_folder = base_folder + "files/"


class ParanoTestCases(unittest.TestCase):


	def _setUp(self):
		self.p = parano.Parano()
		self.p.window_main.hide()

	def _tearDown(self):
		self.p = None

	def _save(self, format):
		for f in glob.glob( test_folder + "*"):
			if os.path.isdir(f):
				continue
			local = os.path.abspath(f)
			uri = gnomevfs.get_uri_from_local_path(local)
			self.p.add_file(uri)
		local = os.path.abspath("test/test.%s" % format)
		uri = gnomevfs.get_uri_from_local_path(local)
		self.p.save_hashfile(uri)
		return uri

	def _load(self, uri):
		self.p.new_hashfile()
		self.p.load_hashfile(uri)

	def _testSave(self, format):
		uri = self._save(format)
		self._load(uri)
		changed, missing, error = self.p.update_file_list()
		if changed or missing or error:
			self.assert_(False, "hash mismatch with format %s" % format)

	def _testCorrupt(self, format):
		f = file(test_folder + "corrupted", "w")
		f.write("this is the normal text")
		f.close()
		uri = self._save(format)
		f = file(test_folder + "corrupted", "w")
		f.write("this is the corrupted text")
		f.close()
		self._load(uri)
		changed, missing, error = self.p.update_file_list()
		self.assert_( 
			changed == 1 and missing == 0 and error == 0
			, "corruption not detected with format %s" % format)
		os.unlink(test_folder + "corrupted")

	def _testMissing(self, format):
		f = file(test_folder + "missing", "w")
		f.write("this is the normal text")
		f.close()
		uri = self._save(format)
		os.unlink(test_folder + "missing")
		self._load(uri)
		changed, missing, error = self.p.update_file_list()
		self.assert_( 
			changed == 0 and missing == 1 and error == 0
			, "corruption not detected with format %s" % format)

	def _testError(self, format):
		f = file(test_folder + "error", "w")
		f.write("this is the normal text")
		f.close()
		uri = self._save(format)
		os.chmod(test_folder + "error",0)
		self._load(uri)
		changed, missing, error = self.p.update_file_list()
		os.chmod( test_folder + "error", 0666)
		os.unlink(test_folder + "error")
		self.assert_( 
			changed == 0 and missing == 0 and error == 1
			, "corruption not detected with format %s" % format)


	def callTest(self, test):
		for format in ("sfv", "md5", "sha1"):
			self._setUp()
			test(format)
			self._tearDown()
	def testSave(self):
		self.callTest(self._testSave)

	def testCorrupt(self):
		self.callTest(self._testCorrupt)

	def testMissing(self):
		self.callTest(self._testMissing)

	def testError(self):
		self.callTest(self._testError)

	def testRelative(self):
		self._setUp()
		for f in glob.glob( test_folder + "*"):
			if os.path.isdir(f):
				continue
			local = os.path.abspath(f)
			uri = gnomevfs.get_uri_from_local_path(local)
			self.p.add_file(uri)
		local = os.path.abspath("test/relative/test.sfv")
		uri = gnomevfs.get_uri_from_local_path(local)
		self.p.save_hashfile(uri)
		self._tearDown()
	
	def testBackslash(self):
		self._setUp()
		for f in glob.glob( test_folder + "*"):
			if os.path.isdir(f):
				continue
			local = os.path.abspath(f)
			uri = gnomevfs.get_uri_from_local_path(local)
			self.p.add_file(uri)
		local = os.path.abspath("test/backslash.sfv")
		uri = gnomevfs.get_uri_from_local_path(local)
		self.p.save_hashfile(uri)
		self._tearDown()
		
		f = open(local, 'r')
		c = f.read().replace('/','\\')
		f.close()
		f = open(local, 'w')
		f.write(c)
		f.close()
		
		self._setUp()
		self._load(uri)
		changed, missing, error = self.p.update_file_list()

		self.assert_( 
			changed == 0 and missing == 0 and error == 0
			, "")
		self._tearDown()

	def testGetRelative(self):
		self._setUp()

		tests = (
			("file:/yop/test","file:/yop/plop","../test"),
			("file:/yop/test/foo.doc","file:/yop/plop","../test/foo.doc"),
			("file:/yop/test/foo.doc","file:/yop/test","foo.doc"),
			("file:/yop/test/foo.doc","file:/yop/test/","foo.doc"),
			("file:/yop/test","ftp:/yop/plop/foo.md5", None),
		)

		for uri, ref, expected in tests:
			result = self.p.get_relative_filename(uri, ref)
			self.assert_(result == expected, "'%s' != %s" % (result, expected))

		self._tearDown()

	def testMultiple(self):
		self._setUp()
		count=0
		for f in glob.glob( test_folder + "*"):
			if os.path.isdir(f):
				continue
			local = os.path.abspath(f)
			uri = gnomevfs.get_uri_from_local_path(local)
			self.p.new_hashfile()
			self.p.add_file(uri)
			local = os.path.abspath("test/hash-%d.sfv" % count)
			uri = gnomevfs.get_uri_from_local_path(local)
			self.p.save_hashfile(uri)
			count += 1

		self.p.new_hashfile()
		for i in range(count):
			local = os.path.abspath("test/hash-%d.sfv" % i)
			uri = gnomevfs.get_uri_from_local_path(local)
			self.p.load_hashfile(uri)

		self.assert_(len(self.p.files) == count, "%d hashfiles loaded, expected %d" % (len(self.p.files), count))

		self._tearDown()

try:
	os.makedirs(test_folder)
except OSError:
	pass

try:
	os.makedirs(base_folder+"relative")
except OSError:
	pass

def random_file(filename):
	f = file(test_folder + filename, "wb")
	buffer = []
	for i in xrange(randint(1024, 100*1024)):
		buffer.append(chr(randint(0,255)))
	f.write(str(buffer))

def create_test_files():
	random_file("""#é~çà@ '"&{^""")
	random_file("test yop yop")
	random_file("test file")
	random_file("pouët")


if __name__ == "__main__":

	if os.path.exists(test_folder):
		create_test_files()
		unittest.main()
	else:
		print "cannot find", test_folder 

