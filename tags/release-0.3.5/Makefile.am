## Process this file with automake to produce Makefile.in

SUBDIRS = po src mime

CLEANFILES=

EXTRA_DIST = intltool-extract.in intltool-merge.in intltool-update.in autogen.sh
DISTCLEANFILES = intltool-extract intltool-merge intltool-update

## @INTLTOOL_DESKTOP_RULE@

desktopdir = $(datadir)/applications
dist_desktop_DATA = parano.desktop



release: dist
	svn -m "release $(VERSION)" copy . svn+ssh://kassoulet@svn.berlios.de/svnroot/repos/parano/tags/release-$(VERSION)
	lftp -c "open ftp.berlios.de/incoming ; put parano-$(VERSION).tar.gz"




