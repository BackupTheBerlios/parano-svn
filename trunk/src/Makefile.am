## Process this file with automake to produce Makefile.in

appdir = $(bindir)
#app_PYTHON = parano.py
app_SCRIPTS = parano

gladedir = $(datadir)/parano
dist_glade_DATA = parano.png parano-icon.png parano.glade parano.py

pixmapsdir = $(datadir)/pixmaps
pixmaps_DATA = parano-icon.png

EXTRA_DIST = parano.gladep parano.in
CLEANFILES = parano

parano: parano.in
	sed -e s!\@datadir\@!$(gladedir)! < $< > $@
	chmod +x $@
