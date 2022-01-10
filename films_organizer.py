# films_organizer: a command-line application for organizing your films collection

# Sub-commands: generate_base_index, generate_films_index, create_genres_tree, create_directors_tree, create_stars_tree
#               generate_best_actors_index, populate_actors_tree

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

args = argparser.parse_args()
args.exec_func(args)
