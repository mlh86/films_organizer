# films_organizer: a command-line application for organizing your films collection

# Sub-commands: generate_base_index, generate_films_index, create_genres_tree, create_directors_tree, create_stars_tree
#               generate_best_actors_index, populate_actors_tree

import argparse
import glob
import os
import re
import json
from pathlib import Path

def generate_base_index(args_obj):
    libroot = os.path.abspath(args_obj.libdir)
    filmname_pattern = re.compile(args_obj.regex)
    extensions = {".avi",".mkv",".mp4",".m4v",".xvid",".divx"}
    glob_path = libroot
    if args_obj.restrict:
        glob_path = os.path.join(libroot,args_obj.restrict)

    film_files = (p for p in Path(glob_path).rglob("*") if p.suffix in extensions)
    if not film_files:
        print("No film files found under specified directory.")
        return

    numfilms = 0
    films_set = set()
    with open(os.path.join(libroot,"base_index.tsv"),'w',encoding="utf-8") as base_index_file:
        for filepath in film_files:
            fmatch = filmname_pattern.match(filepath.stem)
            if fmatch:
                fname = fmatch.group("filmname").rstrip()
                fyear = fmatch.group("year")
                abspath = os.path.abspath(filepath)
                if args_obj.nodups:
                    ftuple = (fname, fyear)
                    if ftuple in films_set:
                        print("-> Skipping duplicate film at:", abspath)
                        continue
                    films_set.add(ftuple)
                base_index_file.write(fname+"\t"+fyear+"\t"+abspath+"\n")
                numfilms += 1
            else:
                print("-> Could not parse film-name:", filepath)
        print("\n" + str(numfilms), "files added to base_index")


# ------------------------ Argparse Logic ------------------------

argparser = argparse.ArgumentParser(description="A command-line application for organizing your films collection")
subparsers_generator = argparser.add_subparsers()

gbi_cmd = subparsers_generator.add_parser('generate_base_index', aliases=['gbi'])
gbi_cmd.set_defaults(exec_func=generate_base_index)
gbi_cmd.add_argument('libdir', help="The root of your films library, where the index shall be placed")
gbi_cmd.add_argument('--restrict', help='The subfolder of libdir to which base-search should be limited (optional)')
gbi_cmd.add_argument('--regex', default=r'^[([](?P<year>\d{4})[])]\s(?P<filmname>[^[]+)(?:\[|$)',
                                help='The regex pattern to use to parse film-name and film-year out of path\n' \
								    +'The default is ^[([](?P<year>\d{4})[])]\s(?P<filmname>[^[]+)(?:\[|$)')
gbi_cmd.add_argument('--nodups', action='store_true', help="Ignore duplicate entries for the same filmname-&-year")

args = argparser.parse_args()
args.exec_func(args)
