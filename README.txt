films_organizer: A command-line application for organizing your films collection

The purpose of this program is to automatically organize a collection of film files
by director, by genre, or by actor. In order for this to work, the film filenames
should follow a consistent pattern out of which the title and year can be parsed
by the generate_base_index (gbi) command using an appropriate regex.

The default regex parses filenames of the form (year) title [optional-extra-info].ext,
e.g. (1997) Titanic [HD].mkv or (1939) Gone With The Wind.avi. The sub-command
normalize_film_files (nff) tries to convert your film-files to this naming convention
but you can also specify a different regex pattern to generate_base_index if you wish
to maintain a different file-naming convention.

The generate_base_index commands produces a 3-column TSV file, which can then be fed
into the generate_films_index (gfi) command to produce a 6-column TSV via OMDB/IMDB
metadata lookup. The 6 columns are as follows: title, year, director, genres, actors,
filepath.

This 6-column TSV is then used by the create_films_tree command to create a file-folder
tree of films based on director, genres, or actors. By default, hard-links are created
to the original film file for each film entry in this tree, but you can specify the
--create_symlinks option to create symbolic links instead.

Note that the "Films by Actor" tree produced via the method described above is limited
to top-billed actors for each film. If you wish to create a more thorough actor-based
films tree, you can use the generate_actors_list (gal) command followed by the
generate_actors_filmography (gaf) command and then the populate_actors_tree
command.

The gal command gathers the IMDB nmcodes of all actors ever nominated for an
acting Oscar, and then the gaf command fetches their filmography details.
Note that this latter command is particularly time-consuming but it only
needs to be run once. The populate_actors_tree command uses your film
collection's base_index.tsv file along with the filmography file to
populate the "Films by Actor" folder tree.

Please submit any bugs or recommendations to mlh86.pk@outlook.com