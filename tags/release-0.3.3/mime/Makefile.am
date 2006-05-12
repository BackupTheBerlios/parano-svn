
appdir = $(datadir)/application-registry
app_DATA = parano.applications

mimedir = $(datadir)/mime-info
mime_DATA = parano.keys parano.mime

mimexmldir = $(datadir)/mime/packages
mimexml_DATA = parano.xml

EXTRA_DIST = \
	$(app_DATA) \
	$(mime_DATA) \
	$(mimexml_DATA)

install-data-local: install-mimexmlDATA
	update-mime-database $(datadir)/mime

uninstall-local:
	update-mime-database $(datadir)/mime
