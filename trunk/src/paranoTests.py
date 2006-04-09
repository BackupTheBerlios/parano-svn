import unittest
import parano
parano.option_quiet = True
import os
import glob
import gnome
import gnomevfs
import gtk

gnome.init("Parano Test", "wip", gnome.libgnome_module_info_get()) 
parano.DATADIR="."

class ParanoTestCases(unittest.TestCase):

	def setUp(self):
		self.p = parano.Parano()

	def tearDown(self):
		self.p = None

	def never_exists(self, pathname):
		return False

	def always_exists(self, pathname):
		return True

	def _save(self, format):
		for f in glob.glob("../test/files/*"):
			if os.path.isdir(f):
				continue
			local = os.path.abspath(f)
			uri = gnomevfs.get_uri_from_local_path(local)
			self.p.add_file(uri)
		local = os.path.abspath("../test/test.%s" % format)
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
		f = file("../test/files/corrupted", "w")
		f.write("this is the normal text")
		f.close()
		uri = self._save(format)
		f = file("../test/files/corrupted", "w")
		f.write("this is the corrupted text")
		f.close()
		self._load(uri)
		changed, missing, error = self.p.update_file_list()
		self.assert_( 
			changed == 1 and missing == 0 and error == 0
			, "corruption not detected with format %s" % format)

	def _testSaveSFV(self):
		self._testSave("sfv")

	def _testSaveMD5(self):
		self._testSave("md5")

	def testCorruptSFV(self):
		self._testCorrupt("sfv")

	def testCorruptMD5(self):
		self._testCorrupt("md5")


"""
	def testSuffix(self):
		self.g.set_target_suffix(".ogg")
		self.failUnlessEqual(self.g.get_target_name(self.s),
							 "file:///path/to/file.ogg")
	gnome.init(NAME, VERSION, gnome.libgnome_module_info_get()) 

	def testBasename(self):
		self.g.set_target_suffix(".ogg")
		self.g.set_basename_pattern("%(track-number)02d-%(title)s")
		self.failUnlessEqual(self.g.get_target_name(self.s),
							 "file:///path/to/01-Hi_Ho.ogg")

	def testLocation(self):
		self.g.set_target_suffix(".ogg")
		self.g.set_folder("/music")
		self.g.set_subfolder_pattern("%(artist)s/%(album)s")
		self.g.set_basename_pattern("%(track-number)02d-%(title)s")
		self.failUnlessEqual(self.g.get_target_name(self.s),
							 "file:///music/Foo_Bar/IS__TOO/01-Hi_Ho.ogg")

	def testTargetExists(self):
		self.g.set_exists(self.always_exists)
		self.g.set_target_suffix(".ogg")
		self.g.set_folder("/")
		self.failUnlessRaises(TargetNameCreationFailure,
							  self.g.get_target_name,
							  self.s)
"""

if __name__ == "__main__":
	unittest.main()


