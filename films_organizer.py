"""
films_organizer: A command-line application for organizing your films collection

    Copyright (C) 2022  Mohammad L. Hussain

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

The program consists of 7 sub-commands, each with a 3-letter alias:
    - normalize_film_files,
    - generate_base_index, generate_films_index, create_films_tree,
    - generate_actors_list, generate_actors_filmography, populate_actors_tree

    Please submit any bugs or recommendations to mlh86.pk@outlook.com
"""

import argparse
import sys
import os
import re
import json
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


def normalize_film_files(args_obj):
    """
    This function (nff) tries to convert film-names into the format '(year) filmname'
    which is expected by the generate_base_index function. You can supply a custom
    regex to gbi if you wish to use some other naming scheme, but year-info is
    usually needed for exact matching on IMDB for metadata lookup.
    """
    libroot = os.path.abspath(args_obj.libdir)
    extensions = {".avi",".mkv",".mp4",".m4v",".xvid",".divx"}
    film_files = (p for p in Path(libroot).rglob("*") if p.suffix in extensions)
    if not film_files:
        print("No film files found under specified directory.")
        return
    filmname_pattern = re.compile(args_obj.regex)
    for filepath in film_files:
        if filmname_pattern.match(filepath.stem):
            continue
        if args_obj.regex == r"^[([](?P<year>\d{4})[])]\s(?P<filmname>[^[]+)(?:\[|$)" and re.search(r"[([]\d{4}[])]", filepath.stem):
            match = re.search(r"(?P<year>[([]\d{4}[])])", filepath.stem)
            new_stem = re.sub(r'\s[([]\d{4}[])]', '', filepath.stem)
            new_stem = match.group('year') + " " + new_stem
            abspath = os.path.abspath(filepath)
            newpath = abspath.replace(filepath.stem, new_stem)
            os.rename(abspath, newpath)
        else:
            query_url = "http://www.imdb.com/search/title?title_type=feature&" + urlencode({'title':filepath.stem})
            res = _get_url(query_url)
            soup = BeautifulSoup(res.text, 'html.parser')
            film_divs = soup.find_all('div', class_='lister-item mode-advanced')
            abspath = os.path.abspath(filepath)
            if args_obj.interactive and (not film_divs or len(film_divs) > 1):
                print("No exact match found for:", abspath)
                new_stem = input("Enter new file name with year info: ")
                newpath = abspath.replace(filepath.stem, new_stem)
                os.rename(abspath, newpath)
            elif not film_divs:
                print("No IMDB match found for:", abspath)
            elif len(film_divs) > 1:
                print("Multiple IMDB matches found for:", abspath)
                print("-->", query_url)
            else:
                year = film_divs[0].find('span', class_="lister-item-year").text
                if args_obj.postfix_year:
                    new_stem = filepath.stem + " " + year
                else:
                    new_stem = year + " " + filepath.stem
                newpath = abspath.replace(filepath.stem, new_stem)
                os.rename(abspath, newpath)


def generate_base_index(args_obj):
    """
    Creates an index of film files found under the user-specified libdir directory.

    One can use the --restrict option to limit the search to a particular sub-directory of libdir.
    The regex option specifies the pattern to use to parse year and title data out of a filename.
    The default pattern matches filenames of the form "(year) title [optional-extra-info].ext"
    The output of this function is a 3-column base_index.tsv file, where the first
    column is the film title, the second is the year, and the third the filepath.
    """
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


def generate_films_index(args_obj):
    """
    This function uses a 3-column base_index.tsv file to produce a 6-column films_index.tsv file

    The 6-columns hold the title, the year, the director, the genre, the actors, and the filepath
    for each film. The function basically tries to look-up film-data for the films contained in
    base_index.tsv using the OMDB API. A valid OMDB API-key is required for this operation and
    the function will prompt you for such a key. If no valid key is supplied, it falls back
    on doing a IMDB search-&-scrape operation, which is considerably slower. It also resorts
    to an IMDB search whenever it can't find an entry matching a film's title and year via
    OMDB. If a match for a film can't be found on IMDB either, the function adds it to a
    faulty_films_index.tsv for the user to examine later. Note that this function's
    output file is meant to be used by the create_films_tree function.
    """
    try:
        omdb_key = open('omdb_api_key', encoding='utf-8').read()
    except FileNotFoundError:
        omdb_key = input('Please enter your OMDB API key, if you wish to use the OMDB service: ')
        if omdb_key:
            test_query_url = f"http://www.omdbapi.com/?apikey={omdb_key}&i=tt0031381"
            try:
                res = requests.get(test_query_url)
                ftitle = json.loads(res.text).get("Title")
                if ftitle == "Gone with the Wind":
                    with open('omdb_api_key', 'w', encoding='utf-8') as omdb_key_file:
                        omdb_key_file.write(omdb_key)
                        print("OMDB Key Added Successfully")
                else:
                    raise Exception("Invalid API Key entered")
            except Exception:
                print("The API key added seems to be invalid. Please try again.")
                return
    films_count = 1
    verbose = args_obj.verbose
    libroot = os.path.abspath(args_obj.libdir)
    base_index_path = os.path.join(libroot, "base_index.tsv")
    films_index_path = os.path.join(libroot,"films_index.tsv")
    faulty_films_path = os.path.join(libroot,"faulty_films_base_index.tsv")

    if not os.path.exists(base_index_path):
        print("No base_index.tsv file found. Please run the generate_base_index command first.")
        return

    processed_films = set()
    write_mode = "a" if args_obj.mode == 'extend' else "w"
    if args_obj.mode == 'extend' and os.path.exists(films_index_path):
        with open(films_index_path,'r',encoding='utf-8') as films_index:
            print("\nNote: Extending existing films_index.tsv -- only the metadata for missing films will be looked up.\n")
            for film_data in films_index:
                *fdata, filmpath = film_data.strip().split("\t")
                processed_films.add(filmpath)

    with open(base_index_path,'r', encoding="utf-8") as base_index_file:
        with open(films_index_path, write_mode, encoding="utf-8") as films_index_file:
            with open(faulty_films_path, 'w', encoding="utf-8") as faulty_films_file:
                for filmdata in base_index_file:
                    metadata = None
                    filmname, filmyear, filmpath = filmdata.split("\t")
                    if filmpath.strip() in processed_films:
                        continue
                    if verbose:
                        print(f"{films_count:03} - Starting metadata search for: ({filmyear}) {filmname}")
                        films_count += 1
                    if omdb_key:
                        metadata = _do_omdb_search(filmname, filmyear, omdb_key)
                    if not metadata:
                        metadata = _do_imdb_search(filmname, filmyear)
                    if metadata:
                        films_index_file.write("\t".join([filmname,filmyear,metadata['Director'],
                                                         metadata['Genre'],metadata['Actors'],filmpath]))
                    else:
                        print(f"-----> Could not find metadata for: ({filmyear}) {filmname}. Skipping...")
                        faulty_films_file.write("\t".join([filmname,filmyear,filmpath]))
                if not verbose:
                    print("\nFilms-index generated.")
    if not os.path.getsize(faulty_films_path):
        os.remove(faulty_films_path)
    else:
        print("\nCheck the faulty_films_base_index.tsv file for the list of films whose metadata could not be determined." + \
              "\nThis is usually caused by the wrong year being associated with a film-entry or an erroneous title." + \
              "\nYou should fix the files associated with these films and then run the gbi & gfi commands again.")


def create_films_tree(args_obj):
    """
    This function creates a tree of film-files based on a films_index.tsv file and the type-arg specified by the user.

    The type argument can take on three values: director, actor, or genre, and the function proceeds to create
    a directory such as "Fims by Genre" which it populates with sub-folders and links to the original film-files.
    By default, it creates hard-links to the original files but the user can specify the create_symlinks option
    to create symbolic links instead. Note that the films_index.tsv file only includes top-billed actors for
    each film, so the "Films by Actor" tree misses supporting cast members for most films. The other
    functions provided below by this module aim to rectify this situation.
    """
    libroot = os.path.abspath(args_obj.libdir)
    if not os.path.exists(os.path.join(libroot,"films_index.tsv")):
        print("-> No films_index.tsv file found in the specified directory. Aborting...")
        print("-> The generate_base_index and generate_films_index commands need to be run prior to create_* commands")
        return
    tree_dirname = args_obj.dirname or "Films by " + args_obj.type.capitalize()
    tree_rootdir = os.path.join(libroot,tree_dirname)
    if not os.path.exists(tree_rootdir):
        os.mkdir(tree_rootdir)
    os.chdir(tree_rootdir)
    create_link = os.symlink if args_obj.create_symlinks else os.link
    if os.name == 'nt' and args_obj.create_symlinks:
        print("\nNOTE: Creating symbolic-links on Windows requires admin privileges.\n")
    with open(os.path.join(libroot,"films_index.tsv"),'r',encoding="utf-8") as films_index_file:
        for filmdata in films_index_file:
            *name_and_year, directors, genres, actors, filmpath = filmdata.strip().split("\t")
            base_filmname = os.path.basename(filmpath)
            if args_obj.type == 'director':
                data = directors
            elif args_obj.type == 'genre':
                data = genres
            else:
                data = actors
            for datum in data.split(", "):
                if not os.path.exists(datum):
                    os.mkdir(datum)
                linkpath = os.path.join(datum, base_filmname)
                if not os.path.exists(linkpath):
                    if os.path.lexists(linkpath): # Broken symlink...
                        os.remove(linkpath)
                    create_link(filmpath, linkpath)


def generate_actors_list(args_obj):
    """
    Generates a TSV file containing the IMDB nmcodes for all actors nominated for an acting Oscar.

    This function carries out IMDB actor-searches using four Oscar-nominated categories
	in order to get the unique nmcodes of all decent actors, and creates a 3-column
	actors_list.tsv file using the results. Note that users can manually edit this
	list of about 1000 actors to insert the names and nmcodes of their own favorite
	actors (if not already included). This file gets used by the generate_actors_filmography
    function to generate a list of well-rated films for each actor.
    """
    actors_list = []
    for categ in ['actor', 'actress', 'supporting_actor', 'supporting_actress']:
        actor_group = f"oscar_best_{categ}_nominees"
        for start_index in [1,101,201,301]:
            actors_list.extend(_get_imdb_actor_info(actor_group, start_index))
    nmcodes_set = set()
    with open(os.path.join(args_obj.libdir,"actors_list.tsv"),'w',encoding="utf-8") as actors_list_file:
        for actor_data in actors_list:
            if actor_data[0] not in nmcodes_set:
                actors_list_file.write(actor_data[0]+"\t"+actor_data[1]+"\t"+actor_data[2]+"\n")
                nmcodes_set.add(actor_data[0])
        print("-> actors_list.tsv successfully generated")


def generate_actors_filmography(args_obj):
    """
    Uses the actors_list.tsv file to generate a 3-column actors_filmography.tsv file

    This function uses nmcodes from the actors_list.tsv file to find all 'good' films that the
    actor acted in. What counts as a good film depends on the user-defined min_rating option,
    which defaults to 7.0. The first column of the output TSV is the actor's name, the second
    is his or her nmcode, while the third holds a "||"-separated list of film details,
	consisting of the rating, year, and title of each film. This output file is used
	by the populate_actors_tree function to populate a "Films by Actor" folder tree.
    """
    actors_list = os.path.join(args_obj.libdir,"actors_list.tsv")
    if not os.path.exists(actors_list):
        print("Actors-list not found. Please run the generate_actors_list command.")
        return
    with open(os.path.join(args_obj.libdir,"actors_filmography.tsv"),'w',encoding="utf-8") as actors_filmography:
        with open(actors_list,'r',encoding="utf-8") as actors_list:
            for actor_data in actors_list:
                nmcode, actor_type, actor_name = actor_data.strip().split("\t")
                print(f"Fetching filmography for {actor_name}...")
                filmography_string = _get_imdb_actor_filmography(nmcode, actor_type, args_obj.min_rating)
                if filmography_string:
                    actors_filmography.write(actor_name+"\t"+nmcode+"\t"+filmography_string+"\n")


def populate_actors_tree(args_obj):
    """
    Uses actors_filmography.tsv and base_index.tsv to populate the "Films by Actor" folder-tree

    This function basically iterates over the actor-data from the actors_filmography.tsv file,
	trying to find the films from his or her filmography that are available in the local system's
	base_index.tsv file and creating hard-links to such files under the actor's directory folder.
	This creates a link to all of an actor's films instead of being limited to those films
	in which he or she was top-billed.
    """
    base_index_file = os.path.join(args_obj.libdir,"base_index.tsv")
    filmography_file = os.path.abspath(os.path.join(args_obj.libdir,"actors_filmography.tsv"))
    if not os.path.exists(filmography_file):
        print("The actors filmography file could not be found. Please run the generate_actors_filmography command.")
        return
    if not os.path.exists(base_index_file):
        print("The base_index.tsv file could not be found. Please run the generate_base_index command.")
        return

    films_dict = {}
    with open(base_index_file,'r',encoding='utf-8') as base_index:
        for film_data in base_index:
            filmname, filmyear, filmpath = film_data.strip().split("\t")
            films_dict[(filmyear, filmname)] = filmpath

    create_link = os.symlink if args_obj.create_symlinks else os.link
    tree_rootdir = os.path.join(args_obj.libdir,args_obj.dirname)
    if not os.path.exists(tree_rootdir):
        os.mkdir(tree_rootdir)
    os.chdir(tree_rootdir)

    with open(filmography_file,'r',encoding="utf-8") as actors_filmography:
        for actor_data in actors_filmography:
            actor_name, nmcode, filmography = actor_data.strip().split("\t")
            films_list = filmography.split(" || ")
            for film_data in films_list:
                rating, fyear, fname = film_data.split("|")
                if (fyear, fname) in films_dict:
                    filmpath = films_dict[(fyear, fname)]
                    base_filmname = os.path.basename(filmpath)
                    if args_obj.include_ratings:
                        base_filmname = "["+rating+"] "+base_filmname
                    if not os.path.exists(actor_name):
                        os.mkdir(actor_name)
                    linkpath = os.path.join(actor_name, base_filmname)
                    if not os.path.exists(linkpath):
                        if os.path.lexists(linkpath): # Broken symlink...
                            os.remove(linkpath)
                        create_link(filmpath, linkpath)


# ------------------------ INTERNAL FUNCTIONS ------------------------

def _get_url(url):
    res = None
    for i in range(3):
        try:
            res = requests.get(url, timeout=15)
        except Exception:
            if i == 2:
                print(f"Could not fetch the URL ({url}).\nPlease check your internet connection.")
                sys.exit()
            else:
                print("URL Connection Failure. Retrying...")
    return res

def _do_omdb_search(filmname, filmyear, omdb_key):
    query_url = f"http://www.omdbapi.com/?apikey={omdb_key}&" + urlencode({'t':filmname, 'y':filmyear})
    res = _get_url(query_url)
    response = json.loads(res.text)
    if response['Response'] == 'False':
        return None
    return response

def _do_imdb_search(filmname, filmyear):
    min_year = str(int(filmyear) - 1)
    max_year = str(int(filmyear) + 1)
    query_url = f"http://www.imdb.com/search/title?release_date={min_year},{max_year}&" + urlencode({'title':filmname})
    res = _get_url(query_url)
    soup = BeautifulSoup(res.text, 'html.parser')
    film_divs = soup.find_all('div', class_='lister-item mode-advanced')
    if not film_divs:
        return None
    response = {}
    film_div = film_divs[0]
    response['Genre'] = film_div.find('span', class_='genre').text.strip()
    principals_data = film_div.find_all('p')[2].text.replace('|','')
    stars_index = principals_data.find('Stars:')
    director_index = principals_data.find('Director:')
    if director_index == -1:
        director_index = principals_data.find('Directors:')+10
    else:
        director_index += 9
    response['Director'] = principals_data[director_index:stars_index].replace('\n','').strip()
    response['Actors'] = principals_data[stars_index+6:].replace('\n','').strip()
    return response

def _get_imdb_actor_info(actor_group, start_index):
    query_url = f"https://www.imdb.com/search/name/?groups={actor_group}&sort=alpha,asc&count=100&start={start_index}"
    role = 'actress' if 'actress' in actor_group else 'actor'
    print("Fetching next batch of actor data...")
    actor_data = []
    res = _get_url(query_url)
    soup = BeautifulSoup(res.text, 'html.parser')
    actor_blocks = soup.find_all('h3', class_='lister-item-header')
    for block in actor_blocks:
        atag = block.find('a')
        nmcode = atag['href'].split('/')[-1]
        name = atag.text.strip()
        actor_data.append((nmcode,role,name))
    return actor_data

def _get_imdb_actor_filmography(nmcode, actor_type, min_rating):
    filmography_list = []
    for page_num in range(1,4):
        query_url = f"https://www.imdb.com/filmosearch/?page={page_num}&role={nmcode}&job_type={actor_type}&sort=user_rating,desc"
        query_url += "&title_type=movie&explore=title_type&mode=detail"
        res = _get_url(query_url)
        soup = BeautifulSoup(res.text, 'html.parser')
        films = soup.find_all('div', class_='lister-item mode-detail')
        for film in films:
            heading = film.find('h3')
            title = heading.find('a').text.strip().replace("|","")
            year = heading.find('span', class_="lister-item-year").text[1:-1]
            ratings_div = film.find('div', class_='ratings-bar')
            if not ratings_div:
                continue
            rating = ratings_div.find('strong')
            if not rating:
                continue
            rating = float(rating.text)
            if rating >= float(min_rating):
                filmography_list.append(str(rating)+"|"+year+"|"+title)
        if len(filmography_list) < page_num*50:
            break # We only move on to next page if all 50 entries on this page were good
    return " || ".join(filmography_list)


# ------------------------ Argparse Logic ------------------------

argparser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
argparser.usage = "films_organizer.py"
argparser.set_defaults(exec_func=lambda args: print("Please use the -h option to see a list of sub-commands."))
argparser.description = "A command-line application for organizing your films collection.\n" \
                      + "It provides 7 sub-commands, each of which takes its own set of arguments.\n" \
                      + "You can use the -h flag on any subcommand to get its usage details.\n\n" \
                      + "One flow is to use the generate_base_index and the generate_films_index\n" \
                      + "commands, followed by the create_films_tree command to create alternate\n" \
                      + "folder-trees for your films sorted by genre, director, or starring actor.\n\n" \
                      + "You can also use the generate_actors_list, generate_actors_filmography, and\n" \
                      + "populate_actors_tree subcommands to construct a more thorough actor-based tree."
subparsers_generator = argparser.add_subparsers()

nff_cmd = subparsers_generator.add_parser('nff', formatter_class=argparse.RawTextHelpFormatter)
nff_cmd.description = "Tries to normalize film-file names to the format '(year) filmname'\n" \
                    + "by searching for a match on IMDB and extracting year-details from it."
nff_cmd.set_defaults(exec_func=normalize_film_files)
nff_cmd.add_argument('libdir', help="The root of your films library")
nff_cmd.add_argument('--regex', default=r'^[([](?P<year>\d{4})[])]\s(?P<filmname>[^[]+)(?:\[|$)',
                                help='The regex pattern which a normalized file should match.\n' \
                                    +'The default is ^[([](?P<year>\\d{4})[])]\\s(?P<filmname>[^[]+)(?:\\[|$)\n' \
                                    +"which matches titles like '(1997) Titanic' and '[2009] Up'")
nff_cmd.add_argument('--postfix_year',action='store_true')
nff_cmd.add_argument('-i','--interactive',action='store_true')

gbi_cmd = subparsers_generator.add_parser('generate_base_index', aliases=['gbi'], formatter_class=argparse.RawTextHelpFormatter)
gbi_cmd.set_defaults(exec_func=generate_base_index)
gbi_cmd.add_argument('libdir', help="The root of your films library, where the index shall be placed")
gbi_cmd.add_argument('--restrict', help='The subfolder of libdir to which base-search should be limited (optional)')
gbi_cmd.add_argument('--regex', default=r'^[([](?P<year>\d{4})[])]\s(?P<filmname>[^[]+)(?:\[|$)',
                                help='The regex pattern to use to parse film-name and film-year out of path.\n' \
                                    +'The default is ^[([](?P<year>\\d{4})[])]\\s(?P<filmname>[^[]+)(?:\\[|$)\n' \
                                    +'Examples of other regexes are ^(?P<filmname>.+)\\s[([](?P<year>\\d{4})[])]$\n' \
                                    +'and ^(?P<filmname>.+) - (?P<year>\\d{4})$')
gbi_cmd.add_argument('--nodups', action='store_true', help="Ignore duplicate entries for the same filmname-&-year")

gfi_cmd = subparsers_generator.add_parser('generate_films_index', aliases=['gfi'])
gfi_cmd.set_defaults(exec_func=generate_films_index)
gfi_cmd.add_argument('libdir', help="The root of your films library, where the index shall be placed")
gfi_cmd.add_argument('-m', '--mode', action='store', choices=['extend','overwrite'], default='extend')
gfi_cmd.add_argument('-v','--verbose', action='store_true')

cft_cmd = subparsers_generator.add_parser('create_films_tree', aliases=['cft'])
cft_cmd.set_defaults(exec_func=create_films_tree)
cft_cmd.add_argument('libdir', help="The root of your films library, where the folder-tree will be created")
cft_cmd.add_argument('-t','--type', required=True, choices=['director','actor','genre'])
cft_cmd.add_argument('--dirname', default="", help="Custom top-level directory name to use")
cft_cmd.add_argument('--create_symlinks', action='store_true', help="Create symbolic-links instead of hard-links")

gal_cmd = subparsers_generator.add_parser('generate_actors_list', aliases=['gal'])
gal_cmd.set_defaults(exec_func=generate_actors_list)
gal_cmd.add_argument('libdir', help="The root of your films library, where the actors list shall be placed")

gaf_cmd = subparsers_generator.add_parser('generate_actors_filmography', aliases=['gaf'])
gaf_cmd.set_defaults(exec_func=generate_actors_filmography)
gaf_cmd.add_argument('libdir', help="The root of your films library, where the actors filmography shall be placed")
gaf_cmd.add_argument('--min_rating', default="7.0")

pat_cmd = subparsers_generator.add_parser('populate_actors_tree', aliases=['pat'])
pat_cmd.set_defaults(exec_func=populate_actors_tree)
pat_cmd.add_argument('libdir', help="The root of your films library, where the film-folder tree will be created")
pat_cmd.add_argument('--dirname', default="Films by Actor", help="Custom top-level directory name to use")
pat_cmd.add_argument('--include_ratings',action='store_true',help="Include film-rating in file-name")
pat_cmd.add_argument('--create_symlinks', action='store_true', help="Create symbolic-links instead of hard-links")

args = argparser.parse_args()
args.exec_func(args)
