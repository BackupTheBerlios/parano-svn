## Process this file with automake to produce Makefile.in

appdir = $(bindir)
app_SCRIPTS = parano

parano: parano.py
	sed -e s!\@datadir\@!$(datadir)/parano! -e s!\@version\@!$(VERSION)! < $< > $@


gladedir = $(datadir)/parano
dist_glade_DATA = parano.png parano-icon.png parano.glade 

pixmapsdir = $(datadir)/pixmaps
pixmaps_DATA = parano-icon.png

EXTRA_DIST = parano.gladep parano.py
CLEANFILES = parano
