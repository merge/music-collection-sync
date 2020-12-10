#!/usr/bin/env python2

"""
This script synchronizes a music collection recursivly one way from a losless format source directory to a lossy file format target directory.
for Details see README

This software is licensed under the GNU GPLv3 without any warranty as is with ABSOLUTELY NO WARRANTY.
If you find the script useful and would like to donate: UniCredit Bank Austria AG, Gregor Horvath, IBAN: AT47 1100 0014 1436 2200, BIC: BKAUATWW
"""

import os
import sys
import logging
from optparse import OptionParser
import multiprocessing
import time

parser = OptionParser(usage="usage: %prog [options] source_dir target_dir")

parser.add_option("-l", "--loglevel", dest="loglevel", default="INFO",
                  help="set's the log level (ie. the amount of output) possible values: DEBUG, INFO, WARNING, ERROR, CRITICAL")

parser.add_option("-f", "--format", dest="format", default="mp3", type="choice", choices=["ogg","mp3"],
                  help="set the target format to mp3 or ogg (default is mp3)")

parser.add_option("-w", "--target_win", action="store_true", dest="win",
                  help="convert the filenames to Windows convention (for example if you copy to a FAT Partition)")

parser.add_option("-d", "--no_donation", action="store_true", dest="nodonation", default=False,
                  help="suppress the donation message.")

parser.add_option("-s", "--followlinks", action="store_true", dest="followlinks", default=False,
                  help="By default the script will not walk down into symbolic links that resolve to directories. " \
                  "Set followlinks to visit directories pointed to by symlinks, on systems that support them.")

parser.add_option("-r", "--resample", action="store_true", dest="resample", default=False, help="resample to 44.1KHz when converting")

parser.add_option("-m", "--multiprocess", action="store_true", dest="multiprocess", default=False,
                  help="use multiprocessing to convert the files (default is false)")

parser.add_option("-p", "--numberofprocesses", dest="numberofprocesses", default=multiprocessing.cpu_count(), type="int",
                  help="set the number of processes used to convert the files, ignored if multiprocess option is not active" \
                  " (default is the number of detected CPUs)")

(options, args) = parser.parse_args()

if len(args) <> 2:
    parser.error("incorrect number of arguments")
try:
    level = int(getattr(logging, options.loglevel))
except (AttributeError, ValueError, TypeError):
    parser.error("incorrect loglevel value '%s'" % options.loglevel)

for path in args:
    if not os.path.exists(path):
        parser.error("path does not exist: %s" % path)

if args[0] == args[1]:
    parser.error("source and target path must not be the same")
    
if options.win:
    illegal_characters = '?[],\=+<>:;"*|^'
else:
    illegal_characters = ''

target_format = ""

if options.format in ["mp3", "ogg"]:
    target_format = options.format
else:
    parser.error("target format %s not supported" % options.format)

if(options.multiprocess and options.numberofprocesses < 1):
    parser.error("the number of processes must be superior to 0")

logging.basicConfig(level=level)

source_dir = args[0]
target_dir = args[1]

flac_tags_synonyms = {
        "title": ["title"],
        "tracknumber": ["tracknumber"],
        "genre": ["genre"],
        "date": ["date"],
        "artist": ["artist"],
        "album": ["album"],
        "albumartist": ["albumartist"],
        "discnumber": ["discnumber"],
        "totaldiscs": ["totaldiscs", "disctotal"],
        "totaltracks": ["totaltracks", "tracktotal"],
        "composer": ["composer"]}

def create_ID3V2_tag_values_from_flac(source):
    id3_tags_dict = dict.fromkeys(flac_tags_synonyms, "")
    id3_tags_dict['tracknumber'] = "0"
    id3_tags = os.popen("metaflac --export-tags-to=- %s" % shellquote(source)).read().split("\n")
    logging.debug("id3: %s" % id3_tags)
    for id3 in id3_tags:
        if id3:
            try:
                tag, value = id3.split("=", 1)
            except ValueError:
                logging.warning("id3 tag: '%s' ignored." % id3)
            else:
                try:
                    reference_tag = [reference_key for (reference_key, reference_values)
                                     in flac_tags_synonyms.items() if tag.lower() in reference_values][0]
                    if (reference_tag in ["composer", "artist"] and id3_tags_dict[reference_tag] != ""):
                        #tag value is a list, mp3 id3 v2 separator is a /
                        id3_tags_dict[reference_tag] = id3_tags_dict[reference_tag] + "/" + value
                    else:
                        id3_tags_dict[reference_tag] = value
                except IndexError:
                    logging.info("unsupported id3 tag '%s' ignored" % id3)
    for key in id3_tags_dict.keys():
        id3_tags_dict[key] = shellquote(id3_tags_dict[key])
    return id3_tags_dict

def flac_to_mp3(source, target):
    cmd_dict = create_ID3V2_tag_values_from_flac(source)
    cmd_dict['flac_to_mp3_source_flac'] = shellquote(source)
    cmd_dict['flac_to_mp3_target_mp3'] = shellquote(target)
    cmd_dict['flac_to_mp3_enc_opts'] = "-b 192"
    if options.resample:
        cmd_dict['flac_to_mp3_enc_opts'] += " --resample 44.1"

    cmdstr = "flac -cd %(flac_to_mp3_source_flac)s | lame %(flac_to_mp3_enc_opts)s -h --add-id3v2 "\
             "--tt %(title)s " \
             "--tn %(tracknumber)s/%(totaltracks)s " \
             "--tg %(genre)s "\
             "--ty %(date)s "\
             "--ta %(artist)s " \
             "--tl %(album)s " \
             "--tv TPE2=%(albumartist)s " \
             "--tv TPOS=%(discnumber)s/%(totaldiscs)s " \
             "--tv TCOM=%(composer)s " \
             "- %(flac_to_mp3_target_mp3)s" % cmd_dict
    logging.debug(cmdstr)
    os.system(cmdstr)
    # adjust volume with mp3gain
    os.system("mp3gain -r -c -d 10 %(flac_to_mp3_target_mp3)s" % cmd_dict)

def x_to_ogg(source, target):
    oggencopts = "-q8" # 256 kbit/s
    if options.resample:
        oggencopts += " --resample 44100"
    # This automatically copies tags
    cmdstr = "oggenc %s -Q -o %s %s" % (oggencopts, shellquote(target), shellquote(source))
    logging.debug(cmdstr)
    os.system(cmdstr)

def cp(source, target):
    cp_cmd = "copy" if sys.platform.startswith("win") else "cp"
    os.system("%s %s %s" % (cp_cmd, shellquote(source), shellquote(target)))

def wav_to_mp3(source, target):
    # TODO does it copy tags too?
    lame_opts = ""
    if options.resample:
        lame_opts += " --resample 44.1"
    os.system("lame %s -h %s %s" % (lame_opts, shellquote(source), shellquote(target)))

def mkdir(source, target):
    os.system("mkdir %s" % shellquote(target))

convert_map = {"dir":["", mkdir],
               ".ogg":[".ogg", cp],
               ".mp3":[".mp3", cp],
               ".m4a":[".m4a", cp],
               ".m3u":[".m3u", cp],
               ".jpg":[".jpg", cp],
               ".jpeg":[".jpg", cp]}

if target_format == "ogg":
    convert_map.update({".flac":[".ogg", x_to_ogg],
                        ".wav":[".ogg", x_to_ogg]})
elif target_format == 'mp3':
    convert_map.update({".flac":[".mp3", flac_to_mp3],
                        ".wav":[".mp3", wav_to_mp3]})                                       
                        

def shellquote(s):
    if sys.platform.startswith("win"):
        return "\"" + s.replace('"', '""') + "\""
    else:
        return "'" + s.replace("'", "'\\''") + "'"

def convert(source_fname):
    target_fname = source_fname.replace(source_dir, target_dir)
    cmd = None
    
    if os.path.isdir(source_fname):
        cmd = convert_map["dir"][1] 
    elif os.path.isfile(source_fname) or os.path.islink(source_fname):
        try:
            ext = os.path.splitext(source_fname)[1].lower()
            conv = convert_map[ext]
        except KeyError:
            logging.warning("File extension '%s' not supported." % (ext))
        else:
            target_fname = os.path.splitext(target_fname)[0] + "%s" % conv[0]
            cmd = conv[1] 
    
    else:        
        logging.error("File type not supported.")

    for c in illegal_characters:
        target_fname = target_fname.replace(c, "-")
        
    if not os.path.exists(target_fname):
        if cmd:
            logging.debug("cmd: %s, source: %s, target: %s" % (cmd, source_fname, target_fname))
            cmd(source_fname, target_fname)
        else:
            logging.debug("File '%s' ignored." % source_fname)
        
    else:
        logging.debug("Target '%s' already exists." % target_fname)

def do_single_process(file_list):
    for file in file_list:
        convert(file)

def do_multi_process(file_list):
    pool = None
    try:
        logging.debug("Creating the process pool")
        pool = multiprocessing.Pool(number_of_processes())
        results = pool.map_async(convert, file_list)
        #Specify a timeout in order to receive control-c signal
        result = results.get(0x0FFFFF)
    except KeyboardInterrupt:
        logging.error("Control-c pressed, conversion terminated")
    finally:
        logging.debug("Ensuring the processes are stopped")
        if pool:
            pool.terminate()
        logging.debug("Processes stopped")

def number_of_processes():
    if(options.multiprocess):
        return options.numberofprocesses
    else:
        return 1

def log_elapsed_time(start, end):
    elapsed_time = end - start
    nb_hours, remainder = divmod(elapsed_time, 3600)
    nb_mins, remainder = divmod(remainder, 60)
    nb_secs, remainder = divmod(remainder, 1)
    logging.info("Music collection synchronization performed in %02d:%02d:%02d" % (nb_hours, nb_mins, nb_secs))

if __name__ == '__main__':
    dir_list = []
    file_list = []

    start = time.time()

    for (path, dirs, files) in os.walk(source_dir, followlinks=options.followlinks):
        for dir_name in dirs:
            source = os.path.join(path, dir_name)
            dir_list.append(source)
        for file_name in files:
            source = os.path.join(path, file_name)
            file_list.append(source)

    # The directories are handled first to make sure they all exist when the music files are generated
    logging.info("Starting directory synchronization")
    do_single_process(dir_list)

    if(options.multiprocess and options.numberofprocesses > 1):
        logging.info("Starting file synchronization with %d processes" % number_of_processes())
        do_multi_process(file_list)
    else:
        logging.info("Starting file synchronization with 1 process")
        do_single_process(file_list)

    end = time.time()

    log_elapsed_time(start, end)

    if not options.nodonation:
            print "\nIf you find the script useful and would like to donate: \n" \
                  "UniCredit Bank Austria AG, Gregor Horvath, IBAN: AT47 1100 0014 1436 2200, BIC: BKAUATWW"    
