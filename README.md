# web_get_iplayer
a python wrapper to provide a web interface to get_iplayer 

Put the web_get_iplayer.py in your CGI-BIN directory, make it executable, and then access it via your web browser.
in theory, it will tell you what to do, what directories to create and what permissions to give them.

Note that if it doesn't run at all, run it at the command line to check python has all the libraries it needs.

You also need to have the get_iplayer.pl script installed too, which you get from 
https://sourceforge.net/projects/get-iplayer/


Then set up cron so as to call the wrapper script; you copy the _etc_cron.d_web_get_iplayer to /etc/cron.d
and tweak it to suit your setup. Then make web_get_iplayer.cron.sh executable. These together cause queued
files to be downloaded.

Check /var/lib/web_get_iplayer/ for files and logs etc.