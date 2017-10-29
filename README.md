# web_get_iplayer
a python wrapper to provide a web interface to get_iplayer


## Installation - part 0 - pre-requisites

* install python2 - on ubuntu 16.04, python3 is installed by default, so
  "sudo apt-get install python"

* install an http server that supports cgi-bin, e.g. apache2

* how to enable traditional cgi-bin behaviour in apache/httpd server for
  Debian or Ubuntu:
** cd /etc/apache2/mods-enabled/
** sudo ln -s ../mods-available/cgi.load
** sudo apachectl restart

* download the get_iplayer program from
  https://raw.githubusercontent.com/get-iplayer/get_iplayer/master/get_iplayer
  and put it into the cgi-bin directory and make executable
* on Debian or Ubuntu:
** cd /usr/lib/cgi-bin/
** sudo wget https://raw.githubusercontent.com/get-iplayer/get_iplayer/master/get_iplayer
** sudo chmod ugo+x get_iplayer

* (optional) get the JW Player if you wish to be able to play FLV
  videos embedded in the web page - see instructions in Playback.


## Installation - part 1 - installing this web interface

* download the web_get_iplayer.py from
  wget https://raw.githubusercontent.com/speculatrix/web_get_iplayer/master/web_get_iplayer.py
  and put it into the cgi-bin directory and make executable
* on Debian or Ubuntu:
** cd /usr/lib/cgi-bin/
** sudo wget https://raw.githubusercontent.com/speculatrix/web_get_iplayer/master/web_get_iplayer.py
** sudo chmod ugo+x web_get_iplayer.py


## Installation - part 2 - setting up the web interface's environment

Access the web interace with your web browser, e.g. http://localhost/cgi-bin/web_get_iplayer.py

The program analyses its environment and will tell you what to do,
e.g. what directories to create and what permissions to give them.

Note that if it doesn't run at all, run it at the command line as the httpd
user id to check python has all the libraries it needs, like this:
* $ sudo -i
* # su - wwwrun -s /bin/bash
* $ cd /var/www/cgi-bin
* $ ./web_get_iplayer.py


## Installation - part 3 - the cron queue runner

Set up cron so as to call the wrapper script.

* start a root shell
* change directory to the cgi-bin directory
* get the wrapper script with this command:
  wget https://raw.githubusercontent.com/speculatrix/web_get_iplayer/master/web_get_iplayer.cron.sh
* and make it executable
  chmod ugo+x web_get_iplayer.cron.sh
* get the cron table file with
  wget -O /etc/cron.d/web_get_iplayer https://raw.githubusercontent.com/speculatrix/web_get_iplayer/master/_etc_cron.d_web_get_iplayer
* tweak the /etc/cron.d/web_get_iplayer if your cgi-bin directory is different
* test it, on Debian/Ubuntu to check there are no errors:
** sudo -i
** su - www-data -s /bin/bash
** /usr/lib/cgi-bin/web_get_iplayer.cron.sh

These together run the download queue. You could change the cron tab to run
at night if your bandwidth is cheaper then, or change the frequency at which it
runs if you want to allow your server to idle more.

In case of problems, check files in /var/lib/web_get_iplayer/ which is where
all the queues and logs are kept.


## Playback

You should be able to play back the downloaded files with mplayer, vlc, ffplay etc.

If you want to use the embedded player, you need the JWplayer. In order to
get this, you need to register with the www.jwplayer.com website.

Usually, if you've registered correctly, the download page will be 
https://dashboard.jwplayer.com/#/welcome

Download the jwplayer-*version*.zip file, make a note of the licence key.
Latest at: https://ssl.p.jwpcdn.com/player/download/jwplayer-7.12.8.zip
Unpack the zip file into your htdocs directory, so it appears as 
http://example/jw-player-*version*/ and ensure the appropriate relative URI
is put into the configuration (Flv7Uri) along with the licence key string.


You can transcode the FLV and TS files into other formats to play on other
devices; mp4 is a popular choice. The UI offers this possibility, whereby
it calls a transcode command. A useful script for this is flv-to-divx.sh,
download it and make it executable. A good place to put it is /usr/local/bin,
but you can configure its location.

## Known problems and shortcomings

* sometimes programs don't show up in search but do on
  http://www.bbc.co.uk/iplayer and you have to copy the
  program ID manually into the download function
* audio/radio search is poor at finding programs; reverse engineering
  the http API is not trivial, and is a work in progress
* all the downloaded audio and video files live in the same directory


**How it works**

* the program uses the same web/http API as the android app for searching
* simple json files are used for the queue files
* a cron job runs the queue
* the get_iplayer tool actually does the download, see
  https://github.com/get-iplayer/get_iplayer
* the program simply tabulates the files in the downloads directory

## Tips and Tricks

* Use `--pid-recursive-noclips --pid-recursive` at the end of the `download_args` setting to allow for pids of series and programmes - this will download multiple files.
