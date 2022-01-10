# films_organizer: a command-line application for organizing your films collection

# Sub-commands: generate_base_index, generate_films_index, create_films_tree,
#               generate_actors_list, generate_actors_filmography, populate_actors_tree

import argparse
import glob
import os
import re
import json
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

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


def generate_films_index(args_obj):
    try:
        omdb_key = open('omdb_api_key').read()
    except:
        omdb_key = input('Please enter your OMDB API key, if you wish to use the OMDB service: ')
        if omdb_key:
            test_query_url = f"http://www.omdbapi.com/?apikey={omdb_key}&i=tt0031381"
            try:
                res = requests.get(test_query_url)
                ftitle = json.loads(res.text).get("Title")
                if ftitle == "Gone with the Wind":
                    f = open('omdb_api_key', 'w')
                    f.write(omdb_key)
                    print("OMDB Key Added Successfully")
                else:
                    raise Exception("Invalid API Key entered")
            except Exception:
                print("The API key added seems to be invalid. Please try again.")
                return
    films_count = 1
    verbose = args_obj.verbose
    libroot = os.path.abspath(args_obj.libdir)
    if not os.path.exists(os.path.join(libroot,"base_index.tsv")):
        print("No base_index.tsv file found. Please run the generate_base_index command first.")
        return
    with open(os.path.join(libroot,"base_index.tsv"),'r',encoding="utf-8") as base_index_file:
        with open(os.path.join(libroot,"films_index.tsv"),'w',encoding="utf-8") as films_index_file:
            for filmdata in base_index_file:
                metadata = None
                filmname, filmyear, filmpath = filmdata.split("\t")
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
            if not verbose:
                print("Films-index successfully generated")


def create_films_tree(args_obj):
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
            n, y, directors, genres, actors, filmpath = filmdata.strip().split("\t")
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
        except Exception as e:
            if i == 2:
                raise e
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
    print(principals_data)
    print(director_index, stars_index)
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
        a = block.find('a')
        nmcode = a['href'].split('/')[-1]
        name = a.text.strip()
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

gfi_cmd = subparsers_generator.add_parser('generate_films_index', aliases=['gfi'])
gfi_cmd.set_defaults(exec_func=generate_films_index)
gfi_cmd.add_argument('libdir', help="The root of your films library, where the index shall be placed")
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
