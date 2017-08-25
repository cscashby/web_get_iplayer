#!/usr/bin/python -u
"""
Version: 20170711

For full details, see the README.md in
https://github.com/speculatrix/web_get_iplayer


This script operates in two modes:
 1/ a web wrapper round get_iplayer, written for interoperability testing,
    and to facilitate people with disabilities being able to use iplayer
 2/ a cron job to process the queues

This is a fairly hacky script, written when the BBC terminated the feeds
and broke the indexing/cataloguing functions in get_iplayer

Released under GPLv3 or later by the author, Paul M, in 2015

Get the JW player from here:
    https://account.jwplayer.com/static/download/jwplayer-6.11.zip
Create a jwplayer-6-11 directory in your htdocs directory and unpack the zip,
remove the __MACOSX junk and move the contents of the jwplayer dir up a level


Please forgive the hacky nature of the code, this was my first python program of any size
"""

# pylint:disable=bad-whitespace
# pylint:disable=line-too-long
# pylint:disable=superfluous-parens
# pylint:disable=too-many-lines
# pylint:disable=too-many-locals

import base64
import cgi
import cgitb
import ConfigParser
import hashlib
import json
import os
from os.path import expanduser
import re               # now have two problems
import stat
import sys
import time
import urllib2




#####################################################################################################################
# Globals

# use ConfigParse to manage the settings
my_settings = ConfigParser.ConfigParser()

PATH_OF_SCRIPT = os.path.dirname(os.path.realpath(__file__))

CGI_PARAMS = cgi.FieldStorage()


#####################################################################################################################
# constants

dbg_level = 0   # default value no debug


# the HTML document root (please make a subdirectory called python_errors off webroot which is writable by web daemon)
# this is hopefully the only thing you ever need to change
#DOCROOT_DEFAULT   = '/var/www/html'
DOCROOT_DEFAULT   = '/var/www/public/htdocs'

# state files, queues, logs and so on are stored in this directory
CONTROL_DIR       = '/var/lib/web_get_iplayer'

# the settings file is stored in the control directory
SETTINGS_FILE     = 'web_get_iplayer.settings'
SETTINGS_SECTION  = 'user'

# default values of the settings when being created
SETTINGS_DEFAULTS = { 'http_proxy'          : ''                                , # http proxy, blank if not set
                      'base_url'            : '/iplayer'                        , # relative URL direct to the iplayer files
                      'download_args'       : '--nopurge --nocopyright --flvstreamer ' + PATH_OF_SCRIPT + '/rtmpdump --rtmptvopts "--swfVfy http://www.bbc.co.uk/emp/releases/iplayer/revisions/617463_618125_4/617463_618125_4_emp.swf" --raw --thumb --thumbsize 150',
                      'flash_height'        : '720'                             , # standard flashhd BBC video rez
                      'flash_width'         : '1280'                            , # ...
                      'get_iplayer'         : PATH_OF_SCRIPT + '/get_iplayer'   , # full get_iplayer path
                      'iplayer_directory'   : '/home/iplayer'                   , # file system location of downloaded files
                      'max_recent_items'    : '5'                               , # maximum recent items
                      'max_trnscd_par'      : '1'                               , # maximum transcoding processes in parallel
                      'quality_radio'       : 'best,flashaachigh,flashaacstd'   , # flashaachigh, flashaacstd etc
                      'quality_video'       : 'best,flashhd,flashvhigh'         , # decreasing priority
                      'transcode_cmd'       : '/usr/local/bin/ts-to-mp4.sh'     , # this command is passed two args input & output
                      'Flv5Enable'          : '1'                               , # whether to show the JWplayer 7 column
                      'Flv5Uri'             : '/jwmediaplayer-5.8'              , # URI where the JW "longtail" JW5 player was unpacked
                      'Flv5UriSWF'          : '/player.swf'                     , # the swf of the JW5 player
                      'Flv5UriJS'           : '/swfobject.js'                   , # the jscript of the JW5 player
                      'Flv6Enable'          : '1'                               , # whether to show the JWplayer 7 column
                      'Flv5Key'             : ''                                , # JW Player 5 Key, leave blank if you don't have one
                      'Flv6Uri'             : '/jwplayer-6-11'                  , # URI where the JW "longtail" JW6 player was unpacked
                      'Flv6UriJS'           : '/jwplayer.js'                    , # the jscript of the JW6 player
                      'Flv6Key'             : ''                                , # JW Player 6 Key, leave blank if you don't have one
                      'Flv7Enable'          : '1'                               , # whether to show the JWplayer 7 column
                      'Flv7Uri'             : '/jwplayer-7.7.4'                 , # URI where the JW "longtail" JW7 player was unpacked
                      'Flv7UriJS'           : '/jwplayer.js'                    , # the jscript of the JW6 player
                      'Flv7Key'             : ''                                , # JW Player 7 Key, leave blank if you don't have one
                    }

# which video files to show from the download folder
VIDEO_FILE_SUFFIXES = [ '.avi',
                        '.flv',
                        '.mp4',
                        '.ts',
                      ]

# it seems everybody has the same API key, so we'll use a very common USer AGent string to not draw attention to ourselves
USAG    = 'BBCiPlayer/4.4.0.235 (Nexus5; Android 4.4.4)'
API_KEY = 'q5wcnsqvnacnhjap7gzts9y6'
#API_KEY = 'bLBgJDghrAMaZA1eSFB8TbqOTraEJbUa' # iplayer radio

# these URLs have been discovered using tcpdump whilst watching the android iplayer app
URL_LIST = {
    'config'                : 'http://ibl.api.bbci.co.uk/appconfig/iplayer/android/4.4.0/config.json',
    'highlights'            : 'http://ibl.api.bbci.co.uk/ibl/v1/home/highlights?lang=en&rights=mobile&availability=available&api_key=',
    'popular'               : 'http://ibl.api.bbci.co.uk/ibl/v1/groups/popular/episodes?rights=mobile&page=2&per_page=20&availability=available&api_key=',

    'search_video'          : 'http://search-suggest.api.bbci.co.uk/search-suggest/suggest?q={0}&scope=iplayer&format=bigscreen-2&mediatype=video&mediaset=android-phone-rtmp-high&apikey=' + API_KEY,
    'search_video_by_brand' : 'http://ibl.api.bbci.co.uk/ibl/v1/programmes/{0}?rights=mobile&availability=available&initial_child_count=1&api_key=' + API_KEY,
    'search_episodes_video' : 'http://ibl.api.bbci.co.uk/ibl/v1/programmes/{0}/episodes?rights=mobile&availability=available&page=1&per_page=200&api_key=' + API_KEY,
    'search_video_recomm'   : 'http://ibl.api.bbci.co.uk/ibl/v1/episodes/{0}/recommendations?rights=mobile&availability=available&page=1&per_page=200&api_key=' + API_KEY,

    'search_audio'         : 'http://search-suggest.api.bbci.co.uk/search-suggest/suggest?q={0}&format=suggest&category_site=programmes&category_media_type=audio&apikey=' + API_KEY,
    #'search_audio'          : 'http://data.bbc.co.uk/search-suggest/suggest?q={0}&scope=iplayer&format=bigscreen-2&mediatype=audio&mediaset=android-phone-rtmp-high&apikey=' + API_KEY,
    'search_audio_by_brand' : 'http://ibl.api.bbci.co.uk/ibl/v1/programmes/{0}?rights=mobile&availability=available&mediatype=audio&initial_child_count=1&api_key=' + API_KEY,
    'search_episodes_audio' : 'http://ibl.api.bbci.co.uk/ibl/v1/episodes/{0}?rights=mobile&availability=available&mediatype=audio&api_key=' + API_KEY, #FIXME
    'search_audio_recomm'   : 'http://ibl.api.bbci.co.uk/ibl/v1/episodes/{0}/recommendations?rights=mobile&availability=available&page=1&per_page=200&api_key=' + API_KEY, #FIXME

    'development'           : 'http://ibl.api.bbci.co.uk/ibl/v1/programmes/{0}/episodes?rights=mobile&availability=available&page=1&per_page=200&api_key=' + API_KEY,
    }

MEDIATYPES = { 'video', 'audio', }


HTML_ESCAPE_TABLE = {
    '"': "&quot;"       ,
    "'": "&apos;"       ,
    " ": "+"            ,
}

HTML_UNESCAPE_TABLE = {
    '&quot;':   '"'     ,
    "&apos;":   "'"     ,
    "+":        " "     ,
}

INPUT_FORM_ESCAPE_TABLE = {
    '"': "&quot;"       ,
    "'": "&apos;"       ,
}


QUEUE_FIELDS    = [ 'pid', 'title', 'subtitle', 'TT_submitted', 'TT_started', 'TT_finished', 'mediatype', 'quality', 'transrez', 'force' ]

SUBMIT_QUEUE    = 'submit.txt'  # where the web page submits/enqueues
PENDING_QUEUE   = 'pending.txt' # cron job takes submit and appends to pending
ACTIVE_QUEUE    = 'active.txt'  # the currently running download
COMPLETED_QUEUE = 'completed.txt' # active items added here when done
RECENT_ITEMS    = 'recent.txt'  # recently downloaded
TRNSCDE_SUB_QUEUE    = 'transcode_submit.txt'  # submit queue for transcoding
TRNSCDE_ACT_QUEUE    = 'transcode_active.txt'  # active transcoding


URL_GITHUB_HASH_SELF       = 'https://api.github.com/repos/speculatrix/web_get_iplayer/contents/web_get_iplayer.py'
URL_GITHUB_HASH_GETIPLAYER = 'https://api.github.com/repos/get-iplayer/get_iplayer/contents/get_iplayer'


#####################################################################################################################
def get_github_hash_self():
    """calculates the git hash of the version of this script in github"""

    githubhash = 'UNKNOWN'

    try:
        opener = urllib2.build_opener()
        json_data = json.load(opener.open(URL_GITHUB_HASH_SELF))
        githubhash = json_data['sha']

    except urllib2.HTTPError:
        print 'get_github_hash_self: Exception urllib2.HTTPError'
        githubhash = 'urllib2.HTTPError:'


    return githubhash


#####################################################################################################################
def get_github_hash_get_iplayer():
    """calculates the git hash of the version of the get_iplayer script in github"""

    githubhash = 'UNKNOWN'

    try:
        opener = urllib2.build_opener()
        json_data = json.load(opener.open(URL_GITHUB_HASH_GETIPLAYER))
        githubhash = json_data['sha']

    except urllib2.HTTPError:
        print ('get_github_hash_self: Exception urllib2.HTTPError')
        githubhash = 'urllib2.HTTPError:'


    return githubhash


#####################################################################################################################
def get_githash_self():
    """calculates the git hash of the running script"""

    # stat this file
    fullfile_name = __file__
    fullfile_stat = os.stat(fullfile_name)

    # read this entire file into memory
    fullfile_content = ''
    with open(fullfile_name, 'r') as fullfile_fh:
        fullfile_content = fullfile_fh.read()

    # do what "git hash-object" does
    sha_obj = hashlib.sha1()
    sha_obj.update('blob %d\0' % fullfile_stat.st_size)
    sha_obj.update(fullfile_content)


    return sha_obj.hexdigest()


#####################################################################################################################
def get_githash_get_iplayer():
    """calculates the git hash of the local copy of the get_iplayer script"""

    # stat the get_iplayer file
    fullfile_name = my_settings.get(SETTINGS_SECTION, 'get_iplayer')
    fullfile_stat = os.stat(fullfile_name)

    # read the entire get_iplayer file into memory
    fullfile_content = ''
    with open(fullfile_name, 'r') as fullfile_fh:
        fullfile_content = fullfile_fh.read()

    # do what "git hash-object" does
    sha_obj = hashlib.sha1()
    sha_obj.update('blob %d\0' % fullfile_stat.st_size)
    sha_obj.update(fullfile_content)


    return sha_obj.hexdigest()


#####################################################################################################################
def check_load_config_file():
    """check there's a config file which is writable;
       returns 0 if OK, -1 if the rest of the page should be aborted,
       > 0 to trigger rendering of the settings page"""

    # who am i?
    my_euser_id = os.geteuid()
    my_egroup_id = os.getegid()

    config_bad = 1
    config_file_name = os.path.join(CONTROL_DIR, SETTINGS_FILE)


    ################################################
    # verify that CONTROL_DIR exists and is writable
    try:
        qdir_stat = os.stat(CONTROL_DIR)
    except OSError:
        print 'Error, directory "%s" doesn\'t appear to exist.\n' % (CONTROL_DIR, )
        print 'Please do the following - needs root:\n'
        print '\tsudo mkdir "%s" && sudo chgrp %s "%s" && sudo chmod g+ws "%s"\n' % (CONTROL_DIR, str(my_egroup_id), CONTROL_DIR, CONTROL_DIR)
        config_bad = -1
        return config_bad       # error so severe, no point in continuing


    # owned by me and writable by me, or same group as me and writable through that group?
    if ( (qdir_stat.st_uid == my_euser_id  and (qdir_stat.st_mode & stat.S_IWUSR) != 0)
         or (qdir_stat.st_gid == my_egroup_id and (qdir_stat.st_mode & stat.S_IWGRP) != 0) ):
        #print 'OK, %s exists and is writable' % CONTROL_DIR
        config_bad = 0
    else:
        print 'Error, won\'t be able to write to directory "%s".\n' % (CONTROL_DIR, )
        print 'Please do the following:\n'
        print '\tsudo chgrp %s "%s" && sudo chmod g+ws "%s"\n' % (str(my_egroup_id), CONTROL_DIR, CONTROL_DIR, )
        config_bad = -1
        return config_bad       # error so severe, no point in continuing


    ########
    # verify the settings file exists and is writable
    if not os.path.isfile(config_file_name):
        print 'Error, can\'t open "%s" for reading.\n' % (config_file_name, )
        print 'Please do the following - needs root:\n'
        print '\tsudo touch "%s" && sudo chgrp %s "%s" && sudo chmod g+w "%s"\n' % (config_file_name, str(my_egroup_id), config_file_name, config_file_name)
        config_bad = -1
        return config_bad

    # file is zero bytes?
    config_stat = os.stat(config_file_name)
    if config_stat.st_size == 0:
        print 'Config file is empty, please go to settings and submit to save\n'
        config_bad = 1
        return config_bad

    # owned by me and writable by me, or same group as me and writable through that group?
    if ( ( config_stat.st_uid == my_euser_id  and (config_stat.st_mode & stat.S_IWUSR) != 0)
         or ( config_stat.st_gid == my_egroup_id and (config_stat.st_mode & stat.S_IWGRP) != 0) ):
        config_bad = 0
    else:
        print 'Error, won\'t be able to write to file "%s"\n' % (config_file_name, )
        print 'Please do the following - needs root:\n'
        print '\tsudo chgrp %s "%s" && sudo chmod g+w %s\n' % (config_file_name, my_egroup_id, config_file_name, )
        config_bad = 1
        return config_bad


    ########
    # verify can open the config file, by reading the contents
    try:
        my_settings.read(config_file_name)
        #print 'Debug, successfully opened %s' % (config_file_name, )
        config_bad = 0

    except NameError:
        print 'Fatal Error, failed loading config %s\n' % config_file_name
        config_bad = 1
        return config_bad
    except AttributeError:
        config_bad = 1
        print 'Fatal Error, config %s missing item\n' % config_file_name
        return config_bad

    # check that all the settings we know about were actually created
    # in the my_settings hash
    for setting in SETTINGS_DEFAULTS:
        try:
            my_settings.get(SETTINGS_SECTION, setting)
        except ConfigParser.NoOptionError:
            print 'Warning, there is no settings value for "%s", please go to settings, check values and save<br />' % (setting, )

    ########
    # verify can write in the directory where files are downloaded
    iplayer_directory = ''
    try:
        iplayer_directory = my_settings.get(SETTINGS_SECTION, 'iplayer_directory')
    except ConfigParser.NoOptionError:
        print 'Config appears incomplete, please go to settings and submit to save'
        config_bad = 1
        return config_bad
    except ConfigParser.NoSectionError:
        print 'Config appears incomplete, please go to settings and submit to save'
        config_bad = 1
        return config_bad


    try:
        idir_stat = os.stat(iplayer_directory)
    except OSError:
        print 'Error, directory %s doesn\'t appear to exist.\nPlease do the following - needs root:\n# sudo mkdir %s && sudo chgrp %d %s && sudo chmod g+ws %s\n' % (iplayer_directory, iplayer_directory, my_egroup_id, iplayer_directory, iplayer_directory, )
        config_bad = 1
        return config_bad

    # owned by me and writable by me, or same group as me and writable through that group?
    if ( ( idir_stat.st_uid == my_euser_id and (idir_stat.st_mode & stat.S_IWUSR) != 0)
         or ( idir_stat.st_gid == my_egroup_id and (idir_stat.st_mode & stat.S_IWGRP) != 0) ):
        config_bad = 0
        #print 'Debug, directory "%s" exists and is writable' % (iplayer_directory, )
    else:
        print 'Error, won\'t be able to write to %s\nPlease do the following - needs root:\n# sudo chgrp %d %s && sudo chmod g+ws %s\n' % (iplayer_directory, my_egroup_id, iplayer_directory, iplayer_directory, )
        config_bad = 1
        return config_bad


    # verify that the queue submission file is writable IF it exists
    s_q_f_name = os.path.join(CONTROL_DIR, SUBMIT_QUEUE)
    try:
        qfile_stat = os.stat(s_q_f_name)
        # owned by me and writable by me, or same group as me and writable through that group?
        if ( ( qfile_stat.st_uid == my_euser_id  and (qfile_stat.st_mode & stat.S_IWUSR) != 0)
             or ( qfile_stat.st_gid == my_egroup_id and (qfile_stat.st_mode & stat.S_IWGRP) != 0) ):
            #print 'OK, %s exists and is writable' % (s_q_f_name, )
            config_bad = 0
        else:
            print 'Error, won\'t be able to write to %s\nPlease do the following - needs root:\n# sudo chgrp %d %s && sudo chmod g+w %s\n' % (s_q_f_name, my_egroup_id, CONTROL_DIR, s_q_f_name, )
            config_bad = 1
            return config_bad

    except OSError:     # it's fine for file to not exist
        #print 'OK, %s doesn\'t exist' % (s_q_f_name, )
        config_bad = 0

    #print 'Debug, dropped through to end of check_load_config_file'


    # verify that get_iplayer has a directory to write to
    get_iplayer_dir = os.path.join(expanduser("~"), '.get_iplayer', )
    if not os.path.isdir(get_iplayer_dir):
        print 'Error, directory %s doesn\'t appear to exist.\nPlease do the following - needs root:\n# sudo mkdir %s && sudo chown %d:%d %s && sudo chmod g+ws %s\n' % (get_iplayer_dir, get_iplayer_dir, my_euser_id, my_egroup_id, get_iplayer_dir, get_iplayer_dir, )
        config_bad = 1


    # check that the get_iplayer program exists
    get_iplayer_binary = my_settings.get(SETTINGS_SECTION, 'get_iplayer')
    if not os.path.isfile(get_iplayer_binary):
        print 'Error, get_iplayer program not found.\nPlease fix the configuration for get_iplayer below, or download the program and make it executable with the following commands.\n# sudo wget -O %s https://raw.githubusercontent.com/get-iplayer/get_iplayer/master/get_iplayer\n# sudo chmod ugo+x %s' % (get_iplayer_binary, get_iplayer_binary, )
        config_bad = 1
    # check that the get_iplayer program is executable
    if os.path.isfile(get_iplayer_binary) and not os.access(get_iplayer_binary, os.X_OK):
        print 'Error, get_iplayer program is not executable.\nMake it executable with the following command:\n# sudo chmod ugo+x %s' % (get_iplayer_binary, )
        config_bad = 1


    # need swffile for the rtmpdump program to work
    swffile = expanduser("~") + '/' + '.swfinfo'
    if os.path.isfile(get_iplayer_binary) and not os.path.isfile(swffile):
        print 'Error, file %s doesn\'t appear to exist.\nPlease do the following - needs root:\n# sudo touch %s && sudo chgrp %d: %s && sudo chmod g+w %s\n' % (swffile, swffile, my_egroup_id, swffile, swffile, )
        config_bad = 1


    return config_bad


#####################################################################################################################
def cron_run_queue():
    """ this is the function called when in cron mode """

    # get active queue, if it's not empty, then exit as only one download may be active
    # FIXME! allow multiple active downloads
    active_queue = []
    aqi = 0         # count pending queue entries, -1 if queue couldn't be read
    a_q_f_name = os.path.join(CONTROL_DIR, ACTIVE_QUEUE)
    if os.path.isfile(a_q_f_name):
        aqi = read_queue(active_queue, a_q_f_name)
        if aqi > 0:
            print 'Info, active queue is not empty, so cron job terminating'
            exit(0)


    # get pending queue
    pend_queue = []
    pqi = 0         # count pending queue entries, -1 if queue couldn't be read
    p_q_f_name = os.path.join(CONTROL_DIR, PENDING_QUEUE)
    if os.path.isfile(p_q_f_name):
        pqi = read_queue(pend_queue, p_q_f_name)
        if pqi == -1:
            print 'Error, aborting cron job, couldn\'t read pending queue file'
            exit(1)
    else:
        print 'Info, pending queue file didn\'t exist, it will be created'

    # rename the submission queue file to a temporary name, then sleep.
    # this is to mitigate the race condition of the web interface
    # writing an entry just at that moment.
    sub_queue = []
    sqi = 0         # count submission queue entries, -1 if queue couldn't be read
    s_q_f_name = os.path.join(CONTROL_DIR, SUBMIT_QUEUE)
    s_q_f_tmp_name = s_q_f_name + '.tmp'
    if os.path.isfile(s_q_f_name):
        os.rename(s_q_f_name, s_q_f_tmp_name)
        time.sleep(2)
        sqi = read_queue(sub_queue, s_q_f_tmp_name)
        os.remove(s_q_f_tmp_name)

    if sqi == -1:
        print 'Warn, couldn\'t read submission queue file'
    elif sqi > 0:
        print 'Info, sub_queue is now %s' % (str(sub_queue), )
        pend_queue.extend(sub_queue)
        if write_queue(pend_queue, p_q_f_name) == -1:
            print 'Error, failed writing pending queue item to file %s' % (p_q_f_name, )
    else: # sqi == 0
        print 'Info, submission queue file is empty'


    # recently completed
    recent_queue = []
    rci = 0         # count recent entries, -1 if queue couldn't be read
    r_c_f_name = os.path.join(CONTROL_DIR, RECENT_ITEMS)
    if os.path.isfile(r_c_f_name):
        rci = read_queue(recent_queue, r_c_f_name)
        if rci == -1:
            print 'Error, aborting cron job, couldn\'t read recent items file'
            exit(1)
    else:
        print 'Info, recent items list hasn\'t been created'


    first_item = []
    if len(pend_queue) > 0:
        # pop the first item off the pending queue, and rewrite it
        first_item = pend_queue.pop(0)
        if write_queue(pend_queue, p_q_f_name) == -1:
            print 'Error, failed writing pending queue item to file %s' % (p_q_f_name, )

        first_item['TT_started'] = time.time()
        print 'pending queue now %s' % str(pend_queue)
        active_queue.append( first_item )
        print 'active queue now %s' % str(active_queue)
        if write_queue(pend_queue, p_q_f_name) == -1:
            print 'Error, failed writing submission queue item to %s' % (p_q_f_name, )

        # update active queue
        active_file = os.path.join(CONTROL_DIR, ACTIVE_QUEUE)
        if write_queue(active_queue, active_file) != -1:
            print 'Success, written active item %s to %s' % (str(active_queue), active_file, )
    #else:
        #print 'Pending queue is empty'

    print 'first item on queue %s' % str(first_item)
    if len(first_item) > 0:
        print 'Info, will start downloading %s' % (str(first_item), )

        log_dir = os.path.join(CONTROL_DIR, 'logs')
        if not os.path.isdir(log_dir):
            print 'Info, CONTROL_DIR %s, need to make directory %s' % (CONTROL_DIR, log_dir, )
            os.mkdir(log_dir)
            #os.lchmod(log_dir, 0775)

        output_file = os.path.join(log_dir, first_item['pid'],)

        # assemble the command to call get_iplayer
        cmd = my_settings.get(SETTINGS_SECTION, 'get_iplayer') + ' ' + my_settings.get(SETTINGS_SECTION, 'download_args')

        if first_item['force'] == 'y' :
            cmd = cmd + ' --force'

        if 'transrez' in first_item and first_item['transrez'] != '':
            rezopts = ''
            fnameadd = ''
            if first_item['transrez'] != 'original':
                rezopts = ' -s %s' % (first_item['transrez'], )
                fnameadd = '-%s' % (first_item['transrez'], )
            cmd = cmd + ' --command "' + my_settings.get(SETTINGS_SECTION, 'transcode_cmd') + rezopts + ' <filename> <fileprefix>' + fnameadd + '.avi"'


        # set type - the BBC api uses video/audio, but get_iplayer uses tv/radio
        if first_item['mediatype'] == 'video':
            cmd = cmd + ' --type ' + 'tv'
        else:
            cmd = cmd + ' --type ' + 'radio'

        # set quality mode
        cmd = cmd + ' --modes ' + first_item['quality']

        # set the pid
        cmd = cmd + ' --pid ' + first_item['pid']

        # redirect output
        cmd = cmd + ' > ' + output_file + ' 2>&1'

        print 'background task = %s' % (cmd, )
        os.chdir(my_settings.get(SETTINGS_SECTION, 'iplayer_directory'))

        if dbg_level > 0:
            print 'Cron job is about to run %s' % cmd

        #subprocess.check_call(cmd, stdout=output_file, stderror=output_file)
        os.system(cmd)


        # record when the download completed
        first_item['TT_finished'] = time.time()
        # set active queue empty now the system() call finished
        active_queue = []
        active_file = os.path.join(CONTROL_DIR, ACTIVE_QUEUE)
        if write_queue(active_queue, active_file) == -1:
            print 'Error, failed to write empty active file'
        else:
            print 'Success, written empty active file'

        # append the most recent download to recent and shorten that if needed
        recent_queue.append(first_item)
        while len(recent_queue) >= int(my_settings.get(SETTINGS_SECTION, 'max_recent_items')):
            print 'removing oldest item from recent items queue'
            recent_queue.pop(0)
        if write_queue(recent_queue, r_c_f_name) == -1:
            print 'Error, failed to write recent items file'
        else:
            print 'Success, written recent items file'
    #else:
        #print 'Pending queue is empty, nothing to do'


#####################################################################################################################
def delete_files_by_inode(inode_list, del_img_flag):
    """scan the downloaded list of files and delete any whose inode matches
    one in the list"""

    file_list = os.listdir(my_settings.get(SETTINGS_SECTION, 'iplayer_directory'))

    for file_name in sorted(file_list):
        full_file = os.path.join(my_settings.get(SETTINGS_SECTION, 'iplayer_directory'), file_name)
        if os.path.isfile(full_file):    # need to check file exists in case its a jpg we already deleted
            file_stat = os.stat(full_file)
            #print 'considering file %s which has inode %d\n<br >' % (full_file, file_stat[stat.ST_INO], )

            if str(file_stat[stat.ST_INO]) in inode_list:
                print 'file %s is being deleted \n<br >' % (full_file, )
                try:
                    os.remove(full_file)
                except OSError: # for some reason the above works but throws exception
                    print 'error deleting %s\n<br />' % full_file

                if del_img_flag:
                    file_prefix, _ignore = os.path.splitext(full_file)
                    image_file_name = file_prefix + '.jpg'
                    if os.path.isfile(image_file_name):
                        print 'image %s is being deleted \n<br >' % image_file_name
                        try:
                            os.remove(image_file_name)
                        except OSError: # for some reason the above works but throws exception
                            print 'error deleting %s\n<br />' % (image_file_name, )
                    else:
                        print 'there was no image file %s to be deleted\n<br >' % (image_file_name, )


#####################################################################################################################
def html_escape(text):
    """escape special characters into html"""
    return "".join(HTML_ESCAPE_TABLE.get(c, c) for c in text)


#####################################################################################################################
def html_unescape(in_text):
    """convert html special characters back to text"""

    if (not '&' in in_text) and (not '+' in in_text): # bypass string scan if unnecessary
        return in_text

    out_text = ''
    text_len = len(in_text)
    pos = 0
    while pos < text_len:
        if in_text[pos] == '+':
            out_text += ' '
            pos += 1
        elif in_text[pos] == '&':
            for ukey, uval in HTML_UNESCAPE_TABLE.iteritems():
                ukey_len = len(ukey)
                if in_text[pos:pos+ukey_len] == ukey:
                    out_text += uval
                    pos += ukey_len
        else:
            out_text += in_text[pos]
            pos += 1

    return out_text


#####################################################################################################################
def input_form_escape(text):
    """escape special characters into html input forms"""
    return "".join(INPUT_FORM_ESCAPE_TABLE.get(c, c) for c in text)


#####################################################################################################################
def page_development(p_dev):
    """this page is used for running development experiments"""

    url_key = 'development'
    try:
        print '    <table border="1">'
        print '      <tr>\n        <td colspan="2">Development Page</td>\n      </tr>\n'
        print '      <tr>\n        <td>Query: <form method="get" action=""><input type="hidden" name="page" value="development"><input type="text" name="dev" value="%s" /><input type="submit" /></form>\n        </td>\n      </tr>\n' % (p_dev, )

        if p_dev:
            beforesubst = URL_LIST[url_key]
            url_with_query = beforesubst.format(p_dev)

            opener = urllib2.build_opener()
            opener.addheaders = [('User-agent', USAG)]
            json_data = json.load(opener.open(url_with_query))

            print '      <tr>\n        <td>Result of query<br />\n          %s\n' % (url_with_query, )
            print '        <pre>'
            print json.dumps( json_data, sort_keys=True, indent=4, separators=(',', ': ') )
            print '          </pre>'
            print '        </td>\n      </tr>'

        print '    </table>'

    except urllib2.HTTPError:
        print 'page_development: Exception urllib2.HTTPError'


#####################################################################################################################
def page_download(p_pid, p_mediatype, p_submit, p_title, p_subtitle):
    """ this page presents the download function"""

    if p_pid == '' or p_submit == '':
        # present the chosen pid, or ask for one, and require user to
        # have submitted the request before downloading
        print '  <form method="get" action="">'
        print '  <input type="hidden" name="page" value="download" />'
        print '  <input type="hidden" name="title" value="%s" />' % (p_title, )
        print '  <input type="hidden" name="subtitle" value="%s" />' % (p_subtitle, )
        print '  <table border="0">'
        print '    <tr><td colspan="2">Check details before beginning download</td></tr>\n'
        print '    <tr><td>Program ID</td><td><input type="text" name="pid" value="%s" /></td></tr>' % (p_pid, )
        print '    <tr><td>Title</td><td>'
        if p_title != '':
            print base64.b64decode(p_title)
        print '</td></tr>'
        print '<tr><td>Subtitle</td><td>'
        if p_subtitle != '':
            print base64.b64decode(p_subtitle)
        print '</td></tr>'
        print '      <tr><td>Force redownload</td><td><input type=\"checkbox\" name=\"force_redownload\" /></td></tr>'

        tv_checked = ''
        if p_mediatype == 'video':
            tv_checked = ' checked'

        radio_checked = ''
        if p_mediatype == 'audio':
            radio_checked = ' checked'

        print '    <tr><td>Type</td><td>TV:<input type="radio" name="mediatype" value="video" %s/>&nbsp;&nbsp;Radio:<input type="radio" name="mediatype" value="audio" %s/></td></tr>' % (tv_checked, radio_checked, )
        print '    <tr><td>Transcode Options</td><td>'
        print_select_resolution()
        print '</td></tr>'
        print '    <tr><td>Video Quality</td><td>%s (change in settings then click back)</td></tr>' % (my_settings.get(SETTINGS_SECTION, 'quality_video'), )
        print '    <tr><td>Radio Quality</td><td>%s (change in settings then click back)</td></tr>' % (my_settings.get(SETTINGS_SECTION, 'quality_radio'), )
        #print '    <tr><td colspan="2"><input type="submit" name="submit" value="download" /></td></tr>'
        print '    <tr><td colspan="2"><input type="submit" name="submit" value="enqueue" /></td></tr>'
        print '  </table>'
        print '  </form>'

    else:
        p_force = 'n'
        if 'force_redownload' in CGI_PARAMS :
            p_force = 'y'

        p_transrez = ''
        if 'transrez' in CGI_PARAMS :
            p_transrez = CGI_PARAMS.getvalue('transrez')

        # set type & quality - by default use video mode
        p_quality = my_settings.get(SETTINGS_SECTION, 'quality_video')
        if p_mediatype == 'audio':
            p_quality = my_settings.get(SETTINGS_SECTION, 'quality_radio')

        # create a submission queue item as a dict, so it can be merged with the existing one
        new_sub_q_item = {  'pid'               : p_pid,
                            'title'             : p_title,
                            'subtitle'          : p_subtitle,
                            'TT_submitted'      : time.time(),
                            'TT_started'        : '',
                            'TT_finished'       : '',
                            'mediatype'         : p_mediatype,
                            'quality'           : p_quality,
                            'transrez'          : p_transrez,
                            'force'             : p_force,
                         }

        # read the existing submission queue and extend it
        s_q_f_name = os.path.join(CONTROL_DIR, SUBMIT_QUEUE)

        sub_queue = []
        read_queue(sub_queue, s_q_f_name)
        sub_queue.append(new_sub_q_item)
        if write_queue(sub_queue, s_q_f_name) != -1:
            print 'Success, written queue item to %s' % (s_q_f_name, )


#####################################################################################################################
def page_downloaded(p_dir):
    """this shows a page of media files already downloaded"""


    print '  <form method="get" action="" />'
    print '  <input type="hidden" name="page" value="downloaded" />'
    print '  <input type="checkbox" name="enable_delete" />Enable Delete&nbsp;&nbsp;&nbsp;<input type="checkbox" name="delete_image" />Delete Associated Image<br /><br />'
    print '  <input type="text" name="dir" value="%s"/>Directory<br /><br />' % (p_dir,)

    print '  <table border="0">'
    print '    <tr>'
    print '      <th>&nbsp;</th>'
    if (my_settings.get(SETTINGS_SECTION, 'Flv5Enable') == '1'):
        print '      <th>JWPlayer5</th>'
    if (my_settings.get(SETTINGS_SECTION, 'Flv6Enable') == '1'):
        print '      <th>JWPlayer6</th>'
    if (my_settings.get(SETTINGS_SECTION, 'Flv7Enable') == '1'):
        print '      <th>JWPlayer7</th>'

    print '      <th>Download</th>' \
          '      <th>Transcode</th>'\
          '      <th>Delete</th>'   \
          '      <th>Size KB</th>'  \
          '      <th>Date</th>'     \
          '      <th>Name</th>'     \
          '    </tr>'

    full_dir = "%s/%s" % (my_settings.get(SETTINGS_SECTION, 'iplayer_directory'), p_dir)
    file_list = os.listdir(full_dir)
    for file_item in sorted(file_list):
        file_name, file_extension = os.path.splitext(file_item)
        if file_extension in VIDEO_FILE_SUFFIXES:
            file_stat = os.stat("%s/%s" % (full_dir, file_item, ))
            print '  <tr>'
            print '    <td align="center">',
            file_name_jpg = "%s/%s.jpg" % (full_dir, file_name, )
            if os.path.isfile(file_name_jpg):
                print '<img src="%s/%s/%s.jpg" />' % (my_settings.get(SETTINGS_SECTION, 'base_url'), p_dir, file_name, ),
            else:
                print '&nbsp;',
            print '</td>'
            if (my_settings.get(SETTINGS_SECTION, 'Flv5Enable') == '1'):
                print '    <td align="center"><a href="?page=jwplay5&file=%s&dir=%s"><img src="/icons/movie.png" /></a></td>' % (file_item, p_dir, )
            if (my_settings.get(SETTINGS_SECTION, 'Flv6Enable') == '1'):
                print '    <td align="center"><a href="?page=jwplay6&file=%s&dir=%s"><img src="/icons/movie.png" /></a></td>' % (file_item, p_dir, )
            if (my_settings.get(SETTINGS_SECTION, 'Flv7Enable') == '1'):
                print '    <td align="center"><a href="?page=jwplay7&file=%s&dir=%s"><img src="/icons/movie.png" /></a></td>' % (file_item, p_dir, )
            print '    <td align="center"><a href="%s/%s" target="_new"><img src="/icons/diskimg.png" /></a></td>' % (my_settings.get(SETTINGS_SECTION, 'base_url'), file_item, )
            print '    <td align="center" style="background-image:url(/icons/transfer.png);background-repeat:no-repeat;background-position:center" /><input type="checkbox" name="transcode_inodes" value="%d" />&nbsp;&nbsp;&nbsp;</td>' % (file_stat[stat.ST_INO], )
            print '    <td align="center" style="background-image:url(/icons/burst.png);background-repeat:no-repeat;background-position:center"    /><input type="checkbox" name="delete_inode"    value="%d" />&nbsp;&nbsp;&nbsp;</td>' % (file_stat[stat.ST_INO], )
            print '    <td>%d</td>' % (file_stat.st_size / 1024)
            print '    <td>%s</td>' % time.ctime(file_stat.st_mtime)
            print '    <td>%s</td>' % file_item
            print '  </tr>'
            print '  <tr><td colspan="9"><hr /></td>\n</tr>'

    print '  </table>\n<input type="submit" name="submit" value="GO" />\n</form>\n'


#####################################################################################################################
def page_highlights():
    """this shows the BBCs highlights program listings"""

    url_key = 'highlights'

    try:
        opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', USAG)]
        json_data = json.load(opener.open(URL_LIST[url_key]))

        if dbg_level > 0:
            print '<pre>FULL DUMP OF HIGHLIGHTS RESPONSE'
            print json.dumps( json_data, sort_keys=True, indent=4, separators=(',', ': ') )
            print '</pre>'

        print '  <table border="1">' \
              '    <tr>' \
              '      <th colspan="7">HIGHLIGHTS on TV</th>' \
              '    </tr>' \
              '      <th>Action</th><th>PID</th><th>Type</th><th>Title</th><th>Subtitle</th><th>Synopsis</th><th>Duration</th>'

        print_program_listing_rows(json_data['home_highlights']['elements'], 'video', 'tleo_id')

        print '  </table>' \
              '  </form>'

    except urllib2.HTTPError:
        print 'page_highlights: Exception urllib2.HTTPError'


#####################################################################################################################
def page_illegal_param(illegal_param_count):
    """parameter being passed has invalid format, possibly indicating hack
    attack"""

    print '<h1>Illegal Parameter</h1>'
    print '%d illegal parameters found' % (illegal_param_count, )


#####################################################################################################################
def page_jwplay5(p_dir, p_file):
    """this is the longtail/jwplayer version 5 movie player"""

    print '''
        <script type="text/javascript" src="/jwmediaplayer-5.8/swfobject.js"></script>
        <embed flashvars="file=''' + my_settings.get(SETTINGS_SECTION, 'base_url') + '/' + p_dir + '/' + p_file + '''&autostart=true"
                autostart="false"
                stretching="fill"
                allowfullscreen="true"
                allowscripaccess="always"
                id="player1"
                name="player1"
                src="'''    + my_settings.get(SETTINGS_SECTION, 'Flv5Uri')      + my_settings.get(SETTINGS_SECTION, 'Flv5UriSWF') + '''"
                width="'''  + my_settings.get(SETTINGS_SECTION, 'flash_width')  + '''"
                height="''' + my_settings.get(SETTINGS_SECTION, 'flash_height') + '''"
        />'''


#####################################################################################################################
def page_jwplay6(p_dir, p_file):
    """this is the longtail/jwplayer version 6 movie player"""

    print '    <script type="text/javascript" src="%s%s"></script>' % (my_settings.get(SETTINGS_SECTION, 'Flv6Uri'), my_settings.get(SETTINGS_SECTION, 'Flv6UriJS'), )

    if my_settings.get(SETTINGS_SECTION, 'Flv6Key') != '':
        print '    <script type="text/javascript">jwplayer.key="%s";</script>' % (my_settings.get(SETTINGS_SECTION, 'Flv6Key'), )

    print '''    <div id="myElement">Loading the player...</div>
    <script type="text/javascript">
        jwplayer("myElement").setup({
            file: "''' + my_settings.get(SETTINGS_SECTION, 'base_url') + '/' + p_dir + '/' + p_file + '''",
            fallback: true
        });
    </script>
'''


#####################################################################################################################
def page_jwplay7(p_dir, p_file):
    """this is the longtail/jwplayer version 7 movie player"""

    print '    <script type="text/javascript" src="%s%s"></script>' % (my_settings.get(SETTINGS_SECTION, 'Flv7Uri'), my_settings.get(SETTINGS_SECTION, 'Flv7UriJS'), )

    if my_settings.get(SETTINGS_SECTION, 'Flv7Key') != '':
        print '    <script type="text/javascript">jwplayer.key="%s";</script>' % (my_settings.get(SETTINGS_SECTION, 'Flv7Key'), )

    print '''    <div id="myelement">loading the player...</div>
    <script type="text/javascript">
        jwplayer("myelement").setup({
            file: "''' + my_settings.get(SETTINGS_SECTION, 'base_url') + '/' + p_dir + '/' + p_file + '''",
            fallback: true
        });
    </script>
'''


#####################################################################################################################
def page_popular():
    """this shows the bbcs popular programs listings"""
    url_key = 'popular'

    try:

        # from a url
        #req = urllib2.request(URL_LIST[url_key], headers={ 'user-agent': USAG })
        #json_data = json.load( urllib2.urlopen(req).read() )

        opener = urllib2.build_opener()
        opener.addheaders = [('user-agent', USAG)]
        json_data = json.load(opener.open(URL_LIST[url_key]))

        # from cached copy
        #json_filehandle = open('popular.json')
        #json_data = json.load(json_filehandle)

        if dbg_level > 0:
            print '<pre>'
            print json.dumps( json_data, sort_keys=True, indent=4, separators=(',', ': ') )
            print '</pre>'

        print '  <table border="1">'
        print '    <tr>'
        print '      <th colspan="7">popular on tv</th>'
        print '    </tr>'
        print '      <th>action</th><th>pid</th><th>type</th><th>title</th><th>subtitle</th><th>synopsis</th><th>duration</th>'
        print_program_listing_rows(json_data['group_episodes']['elements'], 'video', 'tleo_id')
        print '  </table>'

    except urllib2.HTTPError:
        print 'page_popular: exception urllib2.httperror'


#####################################################################################################################
def page_queues(p_pid):
    """this shows the current state of queues, and prints a log file that matches the p_pid"""

    print '<h3>current state of queues and logs</h3>'

    # active queue
    print 'active queue:<ol>'
    quefile = os.path.join(CONTROL_DIR, ACTIVE_QUEUE)
    queue = []
    if os.path.isfile(quefile):
        queue_count = read_queue(queue, quefile)    # count queue entries, -1 if queue couldn't be read
        if queue_count == -1:
            print '<b>error</b>, failed reading file'
        elif len(queue) == 0:
            print 'empty'
        else:
            print_queue_as_html_table(queue)
    else:
        print 'hasn\'t been created'
    print '</ol><br />'


    # submission queue
    print 'submission queue:<ol>'
    quefile = os.path.join(CONTROL_DIR, SUBMIT_QUEUE)
    queue = []
    if os.path.isfile(quefile):
        queue_count = read_queue(queue, quefile)
        if queue_count == -1:
            print '<b>error</b>, failed reading file %s' % (quefile, )
        elif len(queue) == 0:
            print 'empty'
        else:
            print_queue_as_html_table(queue)
    else:
        print 'hasn\'t been created'
    print '</ol>\n<br />'


    # pending queue
    print 'pending queue:<ol>'
    quefile = os.path.join(CONTROL_DIR, PENDING_QUEUE)
    queue = []
    if os.path.isfile(quefile):
        queue_count = read_queue(queue, quefile)
        if queue_count == -1:
            print '<b>error</b>, failed reading file'
        elif len(queue) == 0:
            print 'empty'
        else:
            print_queue_as_html_table(queue)
    else:
        print 'hasn\'t been created'
    print '</ol><br />'

    # recently completed
    print 'recent items:<ol>'
    quefile = os.path.join(CONTROL_DIR, RECENT_ITEMS)
    queue = []
    if os.path.isfile(quefile):
        queue_count = read_queue(queue, quefile)
        if queue_count == -1:
            print '<b>error</b>, failed reading file'
        elif len(queue) == 0:
            print 'empty'
        else:
            print_queue_as_html_table(queue)
    else:
        print 'hasn\'t been created'
    print '</ol><br />'

    # basic information
    #file_list = os.listdir(CONTROL_DIR)
    #print '<pre>files in %s are:\n\t%s</pre>\n<br />\n<br />' % (CONTROL_DIR, str(file_list), )

    log_dir = os.path.join(CONTROL_DIR, 'logs')
    if os.path.isdir(log_dir):
        file_list = os.listdir(log_dir)
        print 'Log files in %s:\n<br />\n<ul>' % (log_dir, )
        for log_file_name in file_list:
            print '<a href="?page=queues&pid=%s">%s</a>&nbsp;' % (log_file_name, log_file_name, )
        print '</ul><br />\n<br />'
    else:
        print 'cron job hasn\'t run and made %s yet</pre>\n<br />\n<br />' % log_dir

    print '<a name="loglisting">'
    if p_pid != '':
        log_file_name = os.path.join(CONTROL_DIR, "logs", p_pid)
        if os.path.isfile(log_file_name):
            log_file_handle = open(log_file_name, 'r')
            log_file_contents = log_file_handle.read()
            log_file_handle.close()
            print 'Log for pid: %s\n<br /><ul><pre>%s</pre></ul>' % (p_pid, log_file_contents, )


#####################################################################################################################
def page_recommend(p_pid, p_mediatype):
    """page which finds recommended programs, give it a brand or episode pid"""

    if p_mediatype == 'video' :
        url_key = 'search_video_recomm'
    else:
        url_key = 'search_audio_recomm'

    try:
        beforesubst = URL_LIST[url_key]
        url_with_query = beforesubst.format(p_pid)
        print "page_recommend: pid %s, url_key %s, url %s<br />" % (p_pid, url_key, url_with_query, )

        opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', USAG)]
        json_data = json.load(opener.open(url_with_query))

        print '  <table border="1">'
        print '    <tr>'
        print '    <tr><th colspan="7"><br /><br />Recommendations Related To %s</th></tr>' % (p_pid)

        if 1 or dbg_level > 0:
            print '    <tr><td colspan="7">%s</td></tr>' % (json.dumps(json_data, sort_keys=True, indent=4, separators=(',', ': ') ), )

        print '    <tr>\n      <th>Action</th><th>PID</th><th>Type</th><th>Title</th><th>Subtitle</th><th>Synopsis</th><th>Duration</th>\n    </tr>'
        print_program_listing_rows(json_data['episode_recommendations']['elements'], p_mediatype, 'tleo_id')
        print '  </table>'

    except urllib2.HTTPError:
        print 'page_recommend: Exception urllib2.HTTPError'


#####################################################################################################################
def page_search(p_mediatype, p_sought):
    """page which uses the BBC iplayer API to search for programs which does free-text search"""

    print '<form method="get" action="">'
    print '<input type="hidden" name="page" value="search" />'
    print 'Search term: <input type="text" name="sought" value="%s" />' % (html_unescape(p_sought), )

    print '<select name="mediatype">\n'                 \
          '\t<option value="video">TV</option>\n'       \
          '\t<option value="audio">Radio</option>\n'    \
          '</select>\n'

    print '<input type="submit" name="submit" value="search" />'
    print '</form>'


    if p_sought != '':
        if (p_mediatype == 'video'):
            page_search_video(p_sought)
        elif (p_mediatype == 'audio'):
            print '<b>Work in progress</b><br />'
            page_search_audio(p_sought)

#####################################################################################################################
def page_search_audio(p_sought):
    """page which uses the BBC iplayer API to search for programs which does free-text search"""


    # present data returned by a audio search
    p_mediatype = 'audio'
    print '  <table border="1" width="100%" >\n'
    try:
        print '    <tr>\n      <th colspan="7">%s search results for <i>%s</i></th>\n    </tr>''' % (p_mediatype, html_unescape(p_sought), )
        print '    <tr>\n      <th>Action</th><th>PID</th><th>Type</th><th>Title</th><th>Secondary Title</th><th>Synposis</th>\n    </tr>'
        beforesubst = URL_LIST['search_audio']
        url_with_query = beforesubst.format(html_escape(p_sought))

        opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', USAG)]
        json_data = json.load(opener.open(url_with_query))

        program_data = json_data['results']

        if dbg_level > 1:
            print '    <tr bgcolor="#ddd">\n      <td colspan="7">doing audio search with URL %s' % (url_with_query, )
            print '<pre>=== full json dump of search result ==='
            #print json.dumps( json_data, sort_keys=True, indent=4, separators=(',', ': ') )
            print json.dumps( program_data, sort_keys=True, indent=4, separators=(',', ': ') )
            print '</pre><br/>'
            print '      </td>\n    </tr>'

        if len(program_data):
            # show all the episodes first
            for j_row in program_data:
                #print 'type %s' % (j_row['type'],)
                j_pid = j_row['uri'].split(':')[3]
                j_type = j_row['type']
                j_subtitle = ''
                if 'subtitle' in j_row:
                    j_subtitle = j_row['subtitle']
                j_synopsis = ''
                if 'synopsis' in j_row:
                    j_synopsis = j_row['synopsis']
                j_title = ''
                if 'title' in j_row:
                    j_title = j_row['title']
                #print '    <tr><td colspan="7">%s</td></tr>' % (j_row, )
                print '    <tr>\n'
                if (j_type == 'episode'):
                    b64_title = base64.b64encode(j_title)
                    b64_subtitle = base64.b64encode(j_subtitle)
                    print '      <td>%s</td>\n' % (pid_to_download_link(j_pid, p_mediatype, b64_title, b64_subtitle), )
                elif (j_type == 'brand'):
                    print '      <td>search brand</td>\n'
                elif (j_type == 'series'):
                    print '      <td>search series</td>\n'
                print '      <td>%s</td>\n' \
                      '      <td>%s</td>\n' \
                      '      <td>%s</td>\n' \
                      '      <td>%s</td>\n' \
                      '      <td>%s</td>\n' \
                      '    </tr>' % (j_pid, j_type, j_title, j_subtitle, j_synopsis, )

    except urllib2.HTTPError:
        print 'page_search: Audio Search - Exception urllib2.HTTPError'


#####################################################################################################################
def page_search_video(p_sought):
    """page which uses the BBC iplayer API to search for programs which does free-text search"""


    # present data returned by a video search
    p_mediatype = 'video'
    print '  <table border="1" width="100%" >\n'
    try:
        print '    <tr>\n      <th colspan="7">%s search results for <i>%s</i></th>\n    </tr>''' % (p_mediatype, html_unescape(p_sought), )
        print '    <tr>\n      <th>Action</th><th>PID</th><th>Type</th><th>Title</th><th>Secondary Title</th><th>Synposis</th><th>Duration</th>\n    </tr>'
        beforesubst = URL_LIST['search_video']
        url_with_query = beforesubst.format(html_escape(p_sought))

        opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', USAG)]
        json_data = json.load(opener.open(url_with_query))

        program_data = json_data[1]

        if dbg_level > 0:
            print '    <tr bgcolor="#ddd">\n      <td colspan="7">doing video search with URL %s' % (url_with_query, )
            print '<pre>=== full json dump of search result ==='
            #print json.dumps( json_data, sort_keys=True, indent=4, separators=(',', ': ') )
            print json.dumps( program_data, sort_keys=True, indent=4, separators=(',', ': ') )
            print '</pre><br/>'
            print '      </td>\n    </tr>'

        if len(program_data):
            # show all the episodes first
            for j_row in program_data:
                if j_row['tleo'][0]['type'] == 'episode':
                    search_show_episodes(j_row['tleo'][0]['pid'], p_mediatype)

            #print_program_listing_rows(program_data, 'video', 'pid')
            print '<tr><td colspan="7">&nbsp;</td></tr>'
            #print '<tr><td>'
            for j_row in program_data:
                if j_row['tleo'][0]['type'] != 'episode':
                    #search_show_brand(j_row['tleo'][0]['pid'], p_mediatype)
                    search_show_episodes(j_row['tleo'][0]['pid'], p_mediatype)
                #print 'pid: %s, type: %s, title: %s</br>' % (j_row['tleo'][0]['pid'], j_row['tleo'][0]['type'], j_row['tleo'][0]['title'], )
            #print '</td></tr>'

    except urllib2.HTTPError:
        print 'page_search: Video Search - Exception urllib2.HTTPError'
    print '  </table>\n<br />\n<br />'


    ###############################
    # the data returned by an audio search has a totally different
    # format, despite the query URL being very similar
    p_mediatype = 'video'
    if False:
        print '  <table border="1" width="100%" >\n'
        try:
            print '    <tr>\n      <th colspan="7">Audio search results for <i>%s</i></th>\n    </tr>''' % (p_sought, )
            print '    <tr>\n      <th>Action</th><th>PID</th><th>Type</th><th>Title</th><th>Secondary Title</th><th>Synposis</th><th>Duration</th>\n    </tr>'
            beforesubst = URL_LIST['search_audio']
            url_with_query = beforesubst.format(p_sought)

            opener = urllib2.build_opener()
            opener.addheaders = [('User-agent', USAG)]
            json_data = json.load(opener.open(url_with_query))

            # output of video search different from audio
            program_data = json_data['results']

            if dbg_level > 0:
                print '    <tr bgcolor="#ddd">\n      <td colspan="7">doing audio search with URL %s' % (url_with_query, )
                print '<pre>=== full json dump of search result ==='
                print json.dumps( json_data, sort_keys=True, indent=4, separators=(',', ': ') )
                #print json.dumps( program_data, sort_keys=True, indent=4, separators=(',', ': ') )
                #print '</pre>'
                print '      </td>\n    /tr>'

            if len(program_data):
                print_program_listing_rows(program_data, 'audio', 'pid')

        except urllib2.HTTPError:
            print 'page_search: Audio Search - Exception urllib2.HTTPError'

        print '  </table>'


#####################################################################################################################
def page_settings():
    """the configuration page"""

    config_file_name = os.path.join(CONTROL_DIR, SETTINGS_FILE)

    if os.path.isfile(config_file_name):
        try:
            my_settings.read(config_file_name)

        except ConfigParser.NoSectionError:
            print 'Fatal Error, can\'t open %s for reading <br />' % config_file_name
            return -1
    else:
        print 'Fatal Error, can\'t open settings file %s for reading.<br />' % config_file_name
        return -1


    if SETTINGS_SECTION not in my_settings.sections():
        print 'section %s doesn\'t exit' % SETTINGS_SECTION
        my_settings.add_section(SETTINGS_SECTION)

    print '<form method="get" action="">'
    print '<input type="hidden" name="page" value="settings" />'
    print '<table border="1" width="100%">'


    for setting in SETTINGS_DEFAULTS:
        setting_value = ''

        # get the value if possible from the URL/form
        cgi_param_name = 'c_' + setting
        if cgi_param_name in CGI_PARAMS :
            setting_value = CGI_PARAMS.getvalue(cgi_param_name)
        else:
            # otherwise get it from the config file
            try:
                setting_value = my_settings.get(SETTINGS_SECTION, setting)
            #except AttributeError:
            #except NameError:
            except ConfigParser.NoOptionError:
                print 'failed getting setting %s from config, setting to default' % setting
                # otherwise set it to a default value
                try:
                    setting_value = SETTINGS_DEFAULTS[setting]
                except KeyError:
                    setting_value = ''
                except NameError:
                    setting_value = ''

        my_settings.set(SETTINGS_SECTION, setting, setting_value)


        print '    <tr>\n      <th>%s</th>' % (setting, )
        print '      <td width="75%%"><input type="text" name="c_%s" value="%s" style="display:table-cell; width:100%%" /></td>\n    </tr>' % (setting, input_form_escape(setting_value), )

    print '    <tr>\n     <td colspan="2" ><input type="submit" name="submit" value="submit" /></td>\n    </tr>'
    print '  </table>'
    print '  </form>'

    with open(config_file_name, 'wb') as configfile:
        my_settings.write(configfile)


#####################################################################################################################
def page_transcode(p_submit, p_transcode_inodes):
    """scan the downloaded list of files and transcode any whose inode matches
    one in the list"""

    print 'trancoding files with inodes matching %s\n<br />' % ','.join(p_transcode_inodes)

    if p_submit == '' or p_submit != "Transcode":
        print '<p>Confirm transcode options:</p>'
        print '<form method="get" action="">'
        print '<input type="text" name="transcode_options" value="%s" size="50"><br />' % my_settings.get(SETTINGS_SECTION, 'transcode_cmd')
        print '<input type="submit" name="submit" value="Transcode">'
        for inode_num in p_transcode_inodes:
            print '<input type="hidden" name="transcode_inodes" value="%s">' % (inode_num, )
        print '<input type="hidden" name="page" value="transcode">'
        print '</form>'
    else:
        file_list = os.listdir(my_settings.get(SETTINGS_SECTION, 'iplayer_directory'))

        for file_name in sorted(file_list):
            full_file_name = os.path.join(my_settings.get(SETTINGS_SECTION, 'iplayer_directory'), file_name)
            file_stat = os.stat(full_file_name)
            #print 'considering file %s which has inode %d\n<br >' % (full_file_name, file_stat[stat.ST_INO], )
            if str(file_stat[stat.ST_INO]) in p_transcode_inodes:
                full_file_mp4 = '%s.mp4' % ( os.path.splitext(full_file_name)[0], )
                cmd = '%s %s %s 2>&1' % (my_settings.get(SETTINGS_SECTION, 'transcode_cmd'), full_file_name, full_file_mp4, )
                #print 'file %s is being transcoded with command %s\n<br ><pre>\n' % (full_file_name, cmd, )
                print 'file transcoding<pre>\n%s\n' % (cmd, )
                sys.stdout.flush()
                sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0) # capture stdout
                sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 0) # and stderr
                os.system(cmd)
                print '</pre>'


#####################################################################################################################
def page_upgrade_check():
    """the upgrade check page"""


    ################################################
    # see if this script is up to date
    githubhash_self        = get_github_hash_self()
    githash_self           = get_githash_self()
    githubhash_get_iplayer = get_github_hash_get_iplayer()
    githash_get_iplayer    = get_githash_get_iplayer()

    print '<p>github hash of this file %s<br />\n' % (githubhash_self, )
    print 'git hash of this file %s<br />\n' % (githash_self, )
    print 'github hash of get_iplayer %s<br />\n' % (githubhash_get_iplayer, )
    print 'git hash of get_iplayer %s</p>' % (githash_get_iplayer, )

    print '<p>'
    if (githubhash_self == githash_self):
        print 'Great, this program is the same as the version on github.\n<br />\n'
    else:
        print 'This program appears to be out of date, please update it.\n<br />\n'


    if (githubhash_get_iplayer == githash_get_iplayer):
        print 'Great, the get_iplayer program is the same as the version on github.\n<br />\n'
    else:
        print 'The get_iplayer program appears to be out of date, please update it.\n<br />\n'

    print '</p>'


#####################################################################################################################
def pid_to_download_link(p_pid, p_mediatype, p_title, p_subtitle):
    """a handy helper function to show a pid as a link to the download page"""

    return '<a href="?page=download&pid=%s&mediatype=%s&title=%s&subtitle=%s">download</a>' % (p_pid, p_mediatype, p_title, p_subtitle, )


#####################################################################################################################
def print_queue_as_html_table(q_data):
    """prints a queue as an html table, needs to know expected fields in QUEUE_FIELDS"""

    #print '=== %s ===<br />', (str(q_data), )

    if len(q_data) > 0:
        i = 0
        print '<table border="1">'
        print '\t<tr>'
        for key in QUEUE_FIELDS:
            if key[:3] == 'TT_':
                print '\t\t<th align="center">%s</th>' % (key[3:], )
            else:
                print '\t\t<th align="center">%s</th>' % (key, )
        print '\t</tr>'
        while i < len(q_data):
            print '\t<tr>'

            for key in QUEUE_FIELDS:
            #for key, elem in q_data[i].items():
                if key in q_data[i]:
                    elem = q_data[i][key]
                else:
                    elem = ''

                if key == 'pid':
                    print '\t\t<td align="center">%s<br />' % (elem, )
                    if elem != '':
                        print '<a href="?page=queues&pid=%s">show log</a><br />\n' % (elem, )
                        print '<a href="?page=download&pid=%s&mediatype=%s&title=%s&subtitle=%s">redownload</a><br />\n' % (elem, q_data[i]['mediatype'], q_data[i]['title'], q_data[i]['subtitle'],)
                    else:
                        print '&nbsp;'
                elif key[:3] == 'TT_' and elem != '':
                    print '\t\t<td align="center">%s' % (time.asctime(time.localtime(elem)), ),
                elif key == 'title' or key == 'subtitle':
                    print '\t\t<td align="center">%s' % (base64.b64decode(elem), ),
                else:
                    print '\t\t<td align="center">%s' % (str(elem), ),
                print '      </td>'

            print '\t</tr>'
            i += 1
            #print '\t<tr><td colspan="10"><hr /></td></tr>'
        print '  </table>'
    else:
        print 'empty'

    print '',


#####################################################################################################################
def print_video_listing_rows(j_rows, p_mediatype):
    """this is a helper function which prints programs rows in a standard form"""

    for j_row in j_rows:
        # audio search result dict has additional nesting
        if ('tleo' in j_row and len(j_row['tleo'])):
            prog_item = j_row['tleo'][0]
        else:
            prog_item = j_row

        if dbg_level > 0:
            print '    <tr bgcolor="#ddd">\n      <td colspan="7">print_video_listing_rows: prog_item json is <pre>\n%s</pre></td>\n    </tr>' % (json.dumps( prog_item, sort_keys=True, indent=4, separators=(',', ': ') ), )

        # extract program params and sanitise
        j_type = ''
        if 'type' in prog_item:
            j_type = prog_item['type']

        j_pid = ''
        if 'id' in prog_item:
            j_pid = prog_item['id']
        #elif 'tleo_id' in prog_item:
        #    j_pid = prog_item['tleo_id']
        #if 'pid' in prog_item:
        #    j_pid = prog_item['pid']
        #if 'uri' in prog_item:
        #    j_pid = prog_item['uri'].split(':')[3]

        j_title = ''
        if 'title' in prog_item:
            j_title = unicode(prog_item['title']).encode('ascii', 'ignore')
        j_subtitle = ''
        if 'subtitle' in prog_item:
            j_subtitle = unicode(prog_item['subtitle']).encode('ascii', 'ignore')
        b64_title = base64.b64encode(j_title)
        b64_subtitle = base64.b64encode(j_subtitle)

        j_synsm = ''
        if 'synopsis' in prog_item:
            j_synsm = unicode(prog_item['synopsis']).encode('ascii', 'ignore')
        if 'synopses' in prog_item:
            if 'small' in prog_item['synopses']:
                j_synsm = unicode(prog_item['synopses']['small']).encode('ascii', 'ignore')

        j_duration = ''
        if 'versions' in prog_item:
            if 'duration' in prog_item['versions'][0]:
                if 'text' in prog_item['versions'][0]['duration']:
                    j_duration = prog_item['versions'][0]['duration']['text']

        if (j_type != 'group_large'):
            print '    <tr>\n      <td>',
            if j_type == 'episode':
                print '%s<br />' % (pid_to_download_link(j_pid, p_mediatype, b64_title, b64_subtitle), )
                print '<a href="?page=recommend&pid=%s&mediatype=%s">recommendations</a>' % (j_pid, p_mediatype, )
            #if j_type == 'brand' or j_type == 'series':
            if j_type == 'series':
                print '<a href="?page=episodes&pid=%s&mediatype=%s">more episodes</a>' % (j_pid, p_mediatype, )
            print '&nbsp;</td>'

            print '      <td>%s</td>' % (j_pid, )
            print '      <td>%s</td>' % (j_type, )
            print '      <td>%s</td>' % (j_title, )
            print '      <td>%s</td>' % (j_subtitle, )
            print '      <td>%s</td>' % (j_synsm )
            print '      <td>%s</td>' % (j_duration, )
            print '    </tr>'
            #if j_type == 'brand':
            #    search_show_brand(j_pid, p_mediatype)


#####################################################################################################################
def print_audio_listing_rows(j_rows, p_mediatype):
    """this is a helper function which prints programs rows in a standard form"""

    for j_row in j_rows:
        # audio search result dict has additional nesting
        if ('tleo' in j_row and len(j_row['tleo'])):
            prog_item = j_row['tleo'][0]
        else:
            prog_item = j_row

        if dbg_level > 0:
            print '    <tr bgcolor="#ddd">\n      <td colspan="7">print_audio_listing_rows: prog_item json is <pre>\n%s</pre></td>\n    </tr>' % (json.dumps( prog_item, sort_keys=True, indent=4, separators=(',', ': ') ), )

        # extract program params and sanitise
        j_type = ''
        if 'type' in prog_item:
            j_type = prog_item['type']

        j_pid = ''
        if 'uri' in prog_item:
            j_pid = prog_item['uri'].split(':')[3]
        if 'pid' in prog_item:
            j_pid = prog_item['pid']

        j_title = ''
        if 'title' in prog_item:
            j_title = unicode(prog_item['title']).encode('ascii', 'ignore')
        j_subtitle = ''
        if 'subtitle' in prog_item:
            j_subtitle = unicode(prog_item['subtitle']).encode('ascii', 'ignore')
        b64_title = base64.b64encode(j_title)
        b64_subtitle = base64.b64encode(j_subtitle)

        j_synsm = ''
        if 'synopsis' in prog_item:
            j_synsm = unicode(prog_item['synopsis']).encode('ascii', 'ignore')
        if 'synopses' in prog_item:
            if 'small' in prog_item['synopses']:
                j_synsm = unicode(prog_item['synopses']['small']).encode('ascii', 'ignore')

        j_duration = ''
        if 'versions' in prog_item:
            if 'duration' in prog_item['versions'][0]:
                if 'text' in prog_item['versions'][0]['duration']:
                    j_duration = prog_item['versions'][0]['duration']['text']

        if (j_type != 'group_large'):
            print '    <tr>\n      <td>',
            if j_type == 'episode':
                print '%s<br />' % (pid_to_download_link(j_pid, p_mediatype, b64_title, b64_subtitle), )
                print '<a href="?page=recommend&pid=%s&mediatype=%s">recommendations</a>' % (j_pid, p_mediatype, )
            #if j_type == 'brand' or j_type == 'series':
            if j_type == 'series':
                print '<a href="?page=episodes&pid=%s&mediatype=%s">more episodes</a>' % (j_pid, p_mediatype, )
            print '&nbsp;</td>'

            print '      <td>%s</td>' % (j_pid, )
            print '      <td>%s</td>' % (j_type, )
            print '      <td>%s</td>' % (j_title, )
            print '      <td>%s</td>' % (j_subtitle, )
            print '      <td>%s</td>' % (j_synsm )
            print '      <td>%s</td>' % (j_duration, )
            print '    </tr>'
            #if j_type == 'brand':
                #search_show_brand(j_pid, p_mediatype)


#####################################################################################################################
def print_program_listing_rows(j_rows, p_mediatype, pid_idx_name):
    """takes a json fragment and turns it into a bunch of rows in a table"""

    if False:
        print 'print_program_listing_rows decoding json as with pid idx name %s<br />' % (pid_idx_name, )
    if (p_mediatype == 'video'):
        print_video_listing_rows(j_rows, p_mediatype)
    else:
        print_audio_listing_rows(j_rows, p_mediatype)

#######################################################################################################################
def print_select_resolution():
    """prints an HTML SELECT of standard resolutions for transcoding"""

    print '<select name="transrez">\n'                               \
          '\t<option value="">Don\'t transcode</option>\n'           \
          '\t<option value="original">original resolution</option>\n'\
          '\t<option value="1920x1080">1920x1080 1080p</option>\n'   \
          '\t<option value="1280x720">1280x720 720p</option>\n'      \
          '\t<option value="1024x600">1024x600 WVGA</option>\n'      \
          '\t<option value="720x576">720x576 PAL</option>\n'         \
          '\t<option value="720x416">720x416 NTSC</option>\n'        \
          '</select>\n'


#####################################################################################################################
def read_queue(queue, queue_file_name):
    """read a queue file and returns number of lines read, or -1 for error"""

    queue_count = -1
    if os.path.isfile(queue_file_name):
        try:
            with open(queue_file_name) as infile:
                queue.extend(json.load(infile))

            infile.close()
            queue_count = len(queue)
        except OSError:
            # ignore when file can't be opened
            print 'Error, read_queue couldn\t open file %s for reading' % (queue_file_name, )

    return(queue_count)


#####################################################################################################################
def search_show_brand(p_brand, p_mediatype):
    """search by brand and expand the result"""


    try:
        url_key = 'search_video_by_brand'
        if p_mediatype == 'audio':
            url_key = 'search_audio_by_brand'

        print '    <tr>\n      <td colspan="7">p_brand is %s, p_mediatype %s,  url_key is %s</td>\n    </tr>' % (p_brand, p_mediatype, url_key, )

        beforesubst = URL_LIST[url_key]
        url_with_query = beforesubst.format(p_brand)

        opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', USAG)]
        json_data = json.load(opener.open(url_with_query))

        print '    <tr>\n      <th colspan="7">%s Search Results For Brand <i>%s</i></th>\n    </tr>' % (p_mediatype, p_brand)
        if dbg_level > 0:
            print '    <tr>\n      <td colspan="7">results of %s brand search with URL %s<pre>' % (p_mediatype, url_with_query)
            print json.dumps( json_data, sort_keys=True, indent=4, separators=(',', ': ') )
            print '</pre></td>\n    </tr>'

        if (len(json_data['programmes']) > 0) and ('initial_children' in json_data['programmes'][0]):
            print_program_listing_rows(json_data['programmes'][0]['initial_children'], p_mediatype, 'id')
        print '    <tr>\n      <th colspan="7">End brand search</th>\n    </tr>'

    except urllib2.HTTPError:
        print '    <tr><td colspan="7">search_show_brand: Exception urllib2.HTTPError</td></tr>'


#####################################################################################################################
def search_show_episodes(p_pid, p_mediatype):
    """page of episodes - pid is a brand - and expand the result"""

    try:
        url_key = 'search_episodes_video'
        if p_mediatype == 'audio':
            url_key = 'search_episodes_audio'

        #print 'sse: p_pid is %s, p_mediatype %s,  url_key is %s\n<br />' % (p_brand, p_mediatype, url_key, )

        beforesubst = URL_LIST[url_key]
        url_with_query = beforesubst.format(p_pid)

        opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', USAG)]
        json_data = json.load(opener.open(url_with_query))

        if dbg_level > 1:
            print '<tr><td colspan="7"><pre>'
            print 'doing episode search by %s with URL %s' % (p_pid, url_with_query, )
            print '=== episode search result ==='
            print json.dumps( json_data, sort_keys=True, indent=4, separators=(',', ': ') )
            print '</pre></td></tr>'


        print '    <tr>'
        print '      <th colspan="7">Episodes for <i>%s</i></th>' % (p_pid, )
        print '    </tr>'
        print '      <th>Action</th><th>PID</th><th>Type</th><th>Title</th><th>Subtitle</th><th>Synopsis</th><th>Duration</th>'
        #if 'episode_recommendations' in json_data and 'elements' in json_data['episode_recommendations']:
        if 'programme_episodes' in json_data:
            if 'elements' in json_data['programme_episodes']:
                print_program_listing_rows(json_data['programme_episodes']['elements'], p_mediatype, 'id')

    except urllib2.HTTPError:
        print 'search_show_episodes: Exception urllib2.HTTPError'


#####################################################################################################################
def web_interface():
    """this is the function which produces the web interface, as opposed
    to the cron function"""

    illegal_param_count = 0

    #print 'Content-Type: text/plain'    # plain text for extreme debugging
    print 'Content-Type: text/html'     # HTML is following
    print                               # blank line, end of headers

    print ''' <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
  "http://www.w3.org/TR/html4/loose.dtd">'''

    print '''
<html>
  <head>
    <title>web get iplayer</title>
    <style type="text/css">
    pre {
      white-space: pre-wrap;       /* Since CSS 2.1 */
      white-space: -moz-pre-wrap;  /* Mozilla, since 1999 */
      white-space: -pre-wrap;      /* Opera 4-6 */
      white-space: -o-pre-wrap;    /* Opera 7 */
      word-wrap: break-word;       /* Internet Explorer 5.5+ */
    }
    </style>

  </head>
<body>
'''

    global dbg_level
    enable_dev_mode = 0
    if ('development' in CGI_PARAMS):
        enable_dev_mode = 1

    if 'dbg_level' in CGI_PARAMS :
        dbg_level = int(CGI_PARAMS.getvalue("dbg_level"))

    if (dbg_level > 0):
        print 'Python errors at <a href="/python_errors" target="_new">/python_errors (new window)</a><br />'


    print '<pre>'
    config_bad = check_load_config_file()
    print '</pre>'
    if config_bad < 0:
        print '<br /><br />cgi-bin cannot do anything useful\n<br />'
    elif config_bad > 0:
        print '<a href="?page=settings">Settings</a>&nbsp;&nbsp;&nbsp;'
        print '<br />\n<br />'
        page_settings()
    else:
        print '''<a href="?page=downloaded">Downloaded</a>&nbsp;&nbsp;&nbsp;
<a href="?page=download">Download</a>&nbsp;&nbsp;&nbsp;
<a href="?page=highlights">Highlights</a>&nbsp;&nbsp;&nbsp;
<a href="?page=popular">Popular</a>&nbsp;&nbsp;&nbsp;
<a href="?page=queues">Queues & Logs</a>&nbsp;&nbsp;&nbsp;
<a href="?page=search">Search</a>&nbsp;&nbsp;&nbsp;
<a href="?page=settings">Settings</a>&nbsp;&nbsp;&nbsp;
<a href="?page=upgrade_check">Upgrade Check</a>&nbsp;&nbsp;&nbsp;'''

        if dbg_level or enable_dev_mode:
            print '<a href="?page=development">Development</a>&nbsp;&nbsp;&nbsp;'
            print '<a href="/python_errors/" target=_new>Python Errors</a>&nbsp;&nbsp;&nbsp;'
        print '<br />\n<br />'


        ########
        # gather all the browser supplied CGI params and validate/sanitise

        if 'enable_delete' in CGI_PARAMS :
            print 'you chose enabled delete\n<br />\n'
            inode_list = CGI_PARAMS.getlist("delete_inode")
            del_img_flag = 0
            if 'delete_image' in CGI_PARAMS :
                del_img_flag = 1
            if len(inode_list) :
                delete_files_by_inode(inode_list, del_img_flag)

        p_dir = ''
        if 'dir' in CGI_PARAMS:
            p_dir = CGI_PARAMS.getvalue('dir')
            if not bool(re.compile('^[0-9A-Za-z-_.]+\Z').match(p_dir)):
                print 'p_dir is illegal\n'
                illegal_param_count += 1


        p_file = ''
        if 'file' in CGI_PARAMS:
            p_file = CGI_PARAMS.getvalue('file')
            if not bool(re.compile('^[0-9A-Za-z-_.]+\Z').match(p_file)):
                print 'p_file is illegal\n'
                illegal_param_count += 1


        p_pid = ''
        if 'pid' in CGI_PARAMS:
            p_pid = CGI_PARAMS.getvalue('pid')
            if not bool(re.compile('^[0-9A-Za-z.]+\Z').match(p_pid)):
                print 'p_pid is illegal\n'
                illegal_param_count += 1

        p_mediatype = ''
        if 'mediatype' in CGI_PARAMS:
            p_mediatype = CGI_PARAMS.getvalue('mediatype')
            if p_mediatype not in MEDIATYPES:
                print 'p_mediatype is illegal\n'
                illegal_param_count += 1

        p_transcode_inodes = []
        if 'transcode_inodes' in CGI_PARAMS:
            p_transcode_inodes = CGI_PARAMS.getlist('transcode_inodes')

        p_sought = ''
        if 'sought' in CGI_PARAMS:
            p_sought = CGI_PARAMS.getvalue('sought')


        p_submit = ''
        if 'submit' in CGI_PARAMS:
            p_submit = CGI_PARAMS.getvalue('submit')


        ########
        # call the specific page
        if illegal_param_count > 0:
            page_illegal_param(illegal_param_count)

        elif 'page' in CGI_PARAMS :

            p_page = CGI_PARAMS.getvalue('page')

            if p_page == 'transcode' or (p_page == 'downloaded' and p_transcode_inodes):
                page_transcode(p_submit, p_transcode_inodes)

            if p_page == 'downloaded' and not p_transcode_inodes:
                page_downloaded(p_dir)

            if p_page == 'download':
                p_title = ''
                if 'title' in CGI_PARAMS:
                    p_title = CGI_PARAMS.getvalue('title')
                p_subtitle = ''
                if 'subtitle' in CGI_PARAMS:
                    p_subtitle = CGI_PARAMS.getvalue('subtitle')
                page_download(p_pid, p_mediatype, p_submit, p_title, p_subtitle)

            if p_page == 'development':
                p_dev = ''
                if 'dev' in CGI_PARAMS:
                    p_dev = CGI_PARAMS.getvalue('dev')
                page_development(p_dev)

            if p_page == 'highlights':
                page_highlights()

            if p_page == 'jwplay5':
                page_jwplay5(p_dir, p_file)

            if p_page == 'jwplay6':
                page_jwplay6(p_dir, p_file)

            if p_page == 'jwplay7':
                page_jwplay7(p_dir, p_file)

            if p_page == 'popular':
                page_popular()

            if p_page == 'queues':
                page_queues(p_pid)

            if p_page == 'recommend':
                page_recommend(p_pid, p_mediatype)

            if p_page == 'search':
                page_search(p_mediatype, p_sought)

            if p_page == 'settings':
                page_settings()

            if p_page == 'upgrade_check':
                page_upgrade_check()

    print '</body>\n</html>'


#####################################################################################################################
def write_queue(queue, queue_file_name):
    """write a queue file which is json format,
       returns -1 on error"""

    error_flag = -1
    try:
        with open(queue_file_name, 'w') as outfile:
            json.dump(queue, outfile)
        outfile.close()
        error_flag = 0
    except OSError:
        print 'Error, write_queue couldn\t open file %s for writing' % (queue_file_name, )

    return(error_flag)


#####################################################################################################################
# main

if len(sys.argv) <= 1:
    DOCROOT = os.environ.get('DOCUMENT_ROOT', DOCROOT_DEFAULT)
    cgitb.enable(display=0, logdir=DOCROOT + '/python_errors', format='html')
    web_interface()

else:
    # need config to be loaded
    if check_load_config_file() != 0:
        print 'Error, checking/loading config and system check failed, use web interface'
        exit(1)

    if sys.argv[1] == '-cron':
        cron_run_queue()
    else:
        print 'Error, unknown argument %s' % (sys.argv[1], )


# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
