
appdir = $(datadir)/application-registry
app_DATA = parano.applications


# The old mime structure 
mimeinfodir = $(datadir)/mime-info
mimeinfo_DATA = parano.mime parano.keys

# The new mime system
mimedir = $(datadir)/mime/packages
mime_DATA = parano.xml

if UPDATE_MIME_DATABASE
install-data-local:
	mkdir -p $(mimedir)
	update-mime-database $(datadir)/mime/

uninstall-local:
	update-mime-database $(datadir)/mime/
else
install-data-local:

uninstall-local:
endif




EXTRA_DIST = \
	$(app_DATA) \
	$(mime_DATA) \
	$(mimeinfo_DATA)
	
