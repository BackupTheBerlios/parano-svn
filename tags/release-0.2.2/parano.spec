Summary: Parano is a GNOME MD5 Frontend.
Name: parano
Version: 0.0.1
Release: 1
License: GPL
BuildArch: noarch
Group: Applications/Security
Source: http://
URL: http://
Packager: Gautier Portet <kassoulet@users.berlios.de>
Requires: python, pygtk2, pygtk2-libglade
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot-%(%{__id_u})

%description
Parano is a GNOME MD5 Frontend. It is written in Python and uses the PyGTK toolkit.
Parano can create, edit and verify md5 files.

%prep
%setup -n parano

%build
#parano is a Python script

%install
make install

%clean
make uninstall

%postun
#Leave nothing behind
rm -Rf /usr/share/parano
rm -Rf /usr/bin/parano

%files
/usr/bin/parano
/usr/share/parano/parano.glade
/usr/share/parano/parano.py
/usr/share/parano/parano.png
/usr/bin/parano

%changelog

